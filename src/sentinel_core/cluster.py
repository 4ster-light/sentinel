"""Cluster instance naming, scale ranges and resize operations"""

from dataclasses import dataclass

from .models import ProcessInfo
from .process import start_process, stop_process
from .state import State

MAX_INSTANCES = 64


@dataclass(frozen=True)
class ScaleSpec:
	"""Inclusive range of instances a cluster may run."""

	min_instances: int
	max_instances: int

	@classmethod
	def parse(cls, raw: str) -> ScaleSpec:
		"""Parse ``N`` or ``MIN-MAX``."""
		low, separator, high = raw.strip().partition("-")
		try:
			minimum = int(low)
			maximum = int(high) if separator else minimum
		except ValueError:
			raise ValueError(f"invalid scale {raw!r}; use N or MIN-MAX") from None
		if minimum < 1:
			raise ValueError("scale minimum must be at least 1")
		if maximum < minimum:
			raise ValueError(f"scale maximum {maximum} is below the minimum {minimum}")
		if maximum > MAX_INSTANCES:
			raise ValueError(f"scale maximum must be at most {MAX_INSTANCES}")
		return cls(minimum, maximum)

	def allows(self, count: int) -> bool:
		return self.min_instances <= count <= self.max_instances

	def describe(self) -> str:
		if self.min_instances == self.max_instances:
			return str(self.min_instances)
		return f"{self.min_instances}-{self.max_instances}"


@dataclass
class ScaleResult:
	started: list[ProcessInfo]
	stopped: list[ProcessInfo]


def instance_name(cluster: str, index: int) -> str:
	return f"{cluster}-{index}"


def cluster_members(state: State, cluster: str) -> list[ProcessInfo]:
	"""Instances recorded for *cluster*, ordered by instance index."""
	return sorted(
		(process for process in state.list_processes() if process.cluster == cluster),
		key=lambda process: process.cluster_index or 0,
	)


def cluster_spec(members: list[ProcessInfo]) -> ScaleSpec:
	"""Range recorded on the cluster's instances."""
	first = members[0]
	return ScaleSpec(
		min_instances=first.cluster_min if first.cluster_min is not None else len(members),
		max_instances=first.cluster_max if first.cluster_max is not None else len(members),
	)


def scale_cluster(state: State, cluster: str, desired: int, *, force: bool = False) -> ScaleResult:
	"""Grow or shrink *cluster* to *desired* instances within its recorded range."""
	members = cluster_members(state, cluster)
	if not members:
		raise ValueError(f"Unknown cluster '{cluster}'")
	spec = cluster_spec(members)
	if not spec.allows(desired):
		raise ValueError(f"Cluster '{cluster}' allows {spec.describe()} instances, not {desired}")

	template = members[0]
	surviving = {member.cluster_index for member in members}
	started: list[ProcessInfo] = []
	stopped: list[ProcessInfo] = []

	for member in members[desired:]:
		stopped.append(stop_process(state, member.id, force=force))
		state.remove_process(member.id)
		surviving.discard(member.cluster_index)

	for index in range(1, desired + 1):
		if index in surviving:
			continue
		started.append(_start_instance(state, template, instance_name(cluster, index), index))

	return ScaleResult(started=started, stopped=stopped)


def _start_instance(state: State, template: ProcessInfo, name: str, index: int) -> ProcessInfo:
	return start_process(
		state,
		template.cmd,
		name=name,
		base_env=template.base_env,
		group=template.group,
		restart=template.restart,
		user=template.user,
		env=template.env,
		env_file=template.env_file,
		cwd=template.cwd,
		health_check=template.health_check,
		startup_timeout_seconds=template.startup_timeout_seconds,
		nice=template.nice,
		ionice_ioclass=template.ionice_ioclass,
		ionice_value=template.ionice_value,
		depends_on=template.depends_on,
		cluster=template.cluster,
		cluster_index=index,
		cluster_min=template.cluster_min,
		cluster_max=template.cluster_max,
	)
