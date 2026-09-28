"""Validated process start options"""

from dataclasses import dataclass

from .state import HealthCheckConfig


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
	nice: int | None = None
	ionice: str | None = None

	def validate(self) -> None:
		"""Raise ValueError describing the first invalid option."""
		if self.startup_timeout_seconds is not None and self.startup_timeout_seconds <= 0:
			raise ValueError("--startup-timeout must be greater than 0")
		if self.instances < 1:
			raise ValueError("--instances must be at least 1")
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
