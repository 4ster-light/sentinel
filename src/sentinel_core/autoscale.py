"""Automatic cluster scaling driven by CPU and memory load"""

import logging
import time
from collections.abc import Callable

from .cluster import ScaleSpec, cluster_members, cluster_spec, scale_cluster
from .models import AutoscaleConfig, ProcessInfo
from .process import ProcessIdentityError, get_process_status, managed_process
from .state import State, serialized

logger = logging.getLogger(__name__)

DEFAULT_COOLDOWN_SECONDS = 30.0


def _is_running(member: ProcessInfo) -> bool:
	try:
		return managed_process(member) is not None
	except ProcessIdentityError:
		return False


def _average_load(members: list[ProcessInfo]) -> tuple[float, float]:
	statuses = [get_process_status(member) for member in members]
	cpu = sum(status.cpu_percent for status in statuses) / len(statuses)
	memory = sum(status.memory_mb for status in statuses) / len(statuses)
	return cpu, memory


def autoscale_decision(
	config: AutoscaleConfig,
	avg_cpu: float,
	avg_memory_mb: float,
	spec: ScaleSpec,
	current: int,
) -> int | None:
	"""Instance count the cluster should run, or None when it should stay.

	Grow while any configured metric is above its high threshold; shrink only
	when every configured metric is below its low threshold, so a hot metric
	blocks scale-down instead of flapping the cluster size.
	"""
	cpu_hot = config.cpu_high is not None and avg_cpu > config.cpu_high
	mem_hot = config.mem_high_mb is not None and avg_memory_mb > config.mem_high_mb
	cpu_cool = config.cpu_low is None or avg_cpu < config.cpu_low
	mem_cool = config.mem_low_mb is None or avg_memory_mb < config.mem_low_mb
	if (cpu_hot or mem_hot) and current < spec.max_instances:
		return current + 1
	if cpu_cool and mem_cool and current > spec.min_instances:
		return current - 1
	return None


@serialized
def apply_autoscaling(
	state: State,
	last_adjusted: dict[str, float],
	cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
	on_scale: Callable[[str, int, int], None] | None = None,
) -> list[tuple[str, int, int]]:
	"""Resize every cluster that carries a scaling policy to match its load.

	Each cluster adjusts by one instance per pass at most, and never more often
	than *cooldown_seconds*; *last_adjusted* maps cluster names to monotonic
	timestamps and is updated in place. The restart pass that revives or
	removes dead instances runs before this one, so members are alive when
	sampled. Returns (cluster, previous, desired) triples.
	"""
	now = time.monotonic()
	adjustments: list[tuple[str, int, int]] = []
	clusters = sorted({info.cluster for info in state.list_processes() if info.cluster})
	for cluster in clusters:
		members = cluster_members(state, cluster)
		config = next((member.autoscale for member in members if member.autoscale is not None), None)
		if config is None:
			continue
		spec = cluster_spec(members)
		running = [member for member in members if _is_running(member)]
		if not running:
			continue
		if now - last_adjusted.get(cluster, 0.0) < cooldown_seconds:
			continue
		avg_cpu, avg_memory_mb = _average_load(running)
		desired = autoscale_decision(config, avg_cpu, avg_memory_mb, spec, current=len(members))
		if desired is None:
			continue
		try:
			scale_cluster(state, cluster, desired)
		except ValueError as e:
			logger.warning("Cannot autoscale cluster '%s': %s", cluster, e)
			continue
		last_adjusted[cluster] = now
		adjustments.append((cluster, len(members), desired))
		if on_scale:
			on_scale(cluster, len(members), desired)
	return adjustments
