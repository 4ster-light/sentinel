"""Validated process start options"""

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from .cluster import ScaleSpec
from .state import AutoscaleConfig, HealthCheckConfig


def parse_ionice_spec(raw: str | None) -> tuple[str | None, int | None]:
	"""Parse an --ionice value into (ioclass, value)."""
	if raw is None or not raw.strip():
		return None, None
	s = raw.strip().lower()
	if s == "idle":
		return "idle", None
	if s == "best-effort" or s.startswith("best-effort:"):
		rest = s.removeprefix("best-effort").lstrip(":").strip()
		if not rest:
			return "best_effort", None
		try:
			value = int(rest)
		except ValueError as e:
			raise ValueError(f"invalid ionice priority in {raw!r}") from e
		if not 0 <= value <= 7:
			raise ValueError("ionice best-effort priority must be between 0 and 7")
		return "best_effort", value
	if s == "realtime" or s.startswith("realtime:"):
		rest = s.removeprefix("realtime").lstrip(":").strip()
		if not rest:
			return "realtime", None
		try:
			value = int(rest)
		except ValueError as e:
			raise ValueError(f"invalid ionice priority in {raw!r}") from e
		if not 0 <= value <= 7:
			raise ValueError("ionice realtime priority must be between 0 and 7")
		return "realtime", value
	raise ValueError("invalid --ionice value (use idle, best-effort[:0-7], or realtime[:0-7])")


def parse_autoscale_specs(specs: Sequence[str]) -> AutoscaleConfig:
	"""Parse repeatable METRIC:HIGH:LOW specs into a scaling policy.

	CPU thresholds are percentages; memory thresholds are megabytes. Each
	metric may be given once, and the thresholds must satisfy 0 < LOW < HIGH.
	"""
	cpu_high: float | None = None
	cpu_low: float | None = None
	mem_high_mb: float | None = None
	mem_low_mb: float | None = None
	for raw in specs:
		metric, separator, rest = raw.strip().partition(":")
		if not separator or metric not in ("cpu", "mem"):
			raise ValueError(f"invalid autoscale spec {raw!r}; use cpu:HIGH:LOW or mem:HIGH:LOW")
		try:
			high, low = [float(part) for part in rest.split(":")]
		except ValueError:
			raise ValueError(f"invalid autoscale spec {raw!r}; use cpu:HIGH:LOW or mem:HIGH:LOW") from None
		if not all(map(math.isfinite, (high, low))) or low <= 0 or low >= high:
			raise ValueError(f"autoscale thresholds in {raw!r} must satisfy 0 < LOW < HIGH")
		if metric == "cpu":
			if cpu_high is not None:
				raise ValueError("--autoscale cpu may only be given once")
			cpu_high, cpu_low = high, low
		else:
			if mem_high_mb is not None:
				raise ValueError("--autoscale mem may only be given once")
			mem_high_mb, mem_low_mb = high, low
	return AutoscaleConfig(cpu_high=cpu_high, cpu_low=cpu_low, mem_high_mb=mem_high_mb, mem_low_mb=mem_low_mb)


@dataclass
class StartOptions:
	"""Options for starting a process, validated independently of the CLI layer."""

	cmd: str
	name: str | None = None
	restart: bool = False
	user: str | None = None
	group: str | None = None
	env_file: str | None = None
	cwd: str | None = None
	health_http: str | None = None
	health_tcp: str | None = None
	health_interval: float = 30.0
	health_timeout: float = 3.0
	health_failures: int = 3
	startup_timeout_seconds: float | None = None
	instances: int = 1
	scale: str | None = None
	autoscale: list[str] = field(default_factory=list)
	depends_on: list[str] = field(default_factory=list)
	nice: int | None = None
	ionice: str | None = None

	def validate(self) -> None:
		"""Raise ValueError describing the first invalid option."""
		if self.startup_timeout_seconds is not None and self.startup_timeout_seconds <= 0:
			raise ValueError("--startup-timeout must be greater than 0")
		if self.instances < 1:
			raise ValueError("--instances must be at least 1")
		if self.scale is not None:
			ScaleSpec.parse(self.scale)
			if self.instances != 1:
				raise ValueError("--scale cannot be combined with --instances")
			if self.depends_on:
				raise ValueError("--scale cannot be combined with --depends-on")
		if self.autoscale:
			parse_autoscale_specs(self.autoscale)
			spec = self.scale_spec
			if spec is None:
				raise ValueError("--autoscale requires --scale with a range, for example --scale 2-4")
			if spec.min_instances == spec.max_instances:
				raise ValueError("--autoscale needs a MIN-MAX range with room to adjust, for example --scale 2-4")
		if any(not dependency.strip() for dependency in self.depends_on):
			raise ValueError("--depends-on requires a process name")
		if self.name is not None and self.name in self.depends_on:
			raise ValueError("--depends-on cannot name the process itself")
		if self.depends_on and self.instances > 1:
			raise ValueError("--depends-on cannot be combined with --instances")
		if self.nice is not None and not -20 <= self.nice <= 19:
			raise ValueError("--nice must be between -20 and 19")
		if self.ionice is not None:
			parse_ionice_spec(self.ionice)
		if self.health_http and self.health_tcp:
			raise ValueError("Use only one of --health-http or --health-tcp")
		if self.health_interval <= 0:
			raise ValueError("--health-interval must be greater than 0")
		if self.health_timeout <= 0:
			raise ValueError("--health-timeout must be greater than 0")
		if self.health_failures < 1:
			raise ValueError("--health-failures must be at least 1")

	@property
	def scale_spec(self) -> ScaleSpec | None:
		"""Parsed instance range, or None when the process is not clustered."""
		return ScaleSpec.parse(self.scale) if self.scale is not None else None

	@property
	def autoscale_config(self) -> AutoscaleConfig | None:
		"""Parsed scaling policy, or None when no autoscale specs were given."""
		return parse_autoscale_specs(self.autoscale) if self.autoscale else None

	@property
	def health_check(self) -> HealthCheckConfig | None:
		if self.health_http:
			return self._health_check("http", self.health_http)
		if self.health_tcp:
			return self._health_check("tcp", self.health_tcp)
		return None

	def _health_check(self, kind: str, target: str) -> HealthCheckConfig:
		return HealthCheckConfig(
			kind=kind,
			target=target,
			interval_seconds=self.health_interval,
			timeout_seconds=self.health_timeout,
			failure_threshold=self.health_failures,
		)

	def ionice_spec(self) -> tuple[str | None, int | None]:
		return parse_ionice_spec(self.ionice) if self.ionice else (None, None)
