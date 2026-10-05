"""State data models

Timestamps are naive local-time ISO 8601 strings. ``create_time`` is the
process creation time reported by psutil and guards against PID reuse.
``env`` holds the variables explicitly requested for a process; ``base_env``
holds the environment captured at first start so restarts do not inherit the
daemon's environment.
"""

from dataclasses import dataclass, field
from typing import Any, Self


@dataclass
class HealthCheckConfig:
	kind: str
	target: str
	interval_seconds: float = 30.0
	timeout_seconds: float = 3.0
	failure_threshold: int = 3

	def to_dict(self) -> dict[str, Any]:
		return {
			"kind": self.kind,
			"target": self.target,
			"interval_seconds": self.interval_seconds,
			"timeout_seconds": self.timeout_seconds,
			"failure_threshold": self.failure_threshold,
		}

	@classmethod
	def from_dict(cls, data: dict[str, Any]) -> Self:
		return cls(
			kind=data["kind"],
			target=data["target"],
			interval_seconds=float(data.get("interval_seconds", 30.0)),
			timeout_seconds=float(data.get("timeout_seconds", 3.0)),
			failure_threshold=int(data.get("failure_threshold", 3)),
		)


@dataclass
class ProcessInfo:
	id: int
	pid: int
	name: str
	cmd: str
	cwd: str
	restart: bool
	started_at: str
	stdout_log: str
	stderr_log: str
	user: str | None = None
	env: dict[str, str] = field(default_factory=dict)
	group: str | None = None
	depends_on: list[str] = field(default_factory=list)
	cluster: str | None = None
	cluster_index: int | None = None
	cluster_min: int | None = None
	cluster_max: int | None = None
	env_file: str | None = None
	health_check: HealthCheckConfig | None = None
	health_failures: int = 0
	health_last_checked_at: str | None = None
	startup_timeout_seconds: float | None = None
	nice: int | None = None
	ionice_ioclass: str | None = None
	ionice_value: int | None = None
	stopped: bool = False
	create_time: float | None = None
	base_env: dict[str, str] | None = None

	def to_dict(self) -> dict[str, Any]:
		return {
			"id": self.id,
			"pid": self.pid,
			"name": self.name,
			"cmd": self.cmd,
			"cwd": self.cwd,
			"restart": self.restart,
			"user": self.user,
			"started_at": self.started_at,
			"stdout_log": self.stdout_log,
			"stderr_log": self.stderr_log,
			"env": dict(self.env),
			"group": self.group,
			"depends_on": self.depends_on,
			"cluster": self.cluster,
			"cluster_index": self.cluster_index,
			"cluster_min": self.cluster_min,
			"cluster_max": self.cluster_max,
			"env_file": self.env_file,
			"health_check": self.health_check.to_dict() if self.health_check else None,
			"health_failures": self.health_failures,
			"health_last_checked_at": self.health_last_checked_at,
			"startup_timeout_seconds": self.startup_timeout_seconds,
			"nice": self.nice,
			"ionice_ioclass": self.ionice_ioclass,
			"ionice_value": self.ionice_value,
			"stopped": self.stopped,
			"create_time": self.create_time,
			"base_env": dict(self.base_env) if self.base_env is not None else None,
		}

	@classmethod
	def from_dict(cls, data: dict[str, Any]) -> Self:
		return cls(
			id=data["id"],
			pid=data["pid"],
			name=data["name"],
			cmd=data["cmd"],
			cwd=data["cwd"],
			restart=data["restart"],
			user=data.get("user"),
			started_at=data["started_at"],
			stdout_log=data["stdout_log"],
			stderr_log=data["stderr_log"],
			env=data.get("env") or {},
			group=data.get("group"),
			depends_on=data.get("depends_on") or [],
			cluster=data.get("cluster"),
			cluster_index=data.get("cluster_index"),
			cluster_min=data.get("cluster_min"),
			cluster_max=data.get("cluster_max"),
			env_file=data.get("env_file"),
			health_check=HealthCheckConfig.from_dict(data["health_check"])
			if data.get("health_check") is not None
			else None,
			health_failures=data.get("health_failures", 0),
			health_last_checked_at=data.get("health_last_checked_at"),
			startup_timeout_seconds=data.get("startup_timeout_seconds"),
			nice=data.get("nice"),
			ionice_ioclass=data.get("ionice_ioclass"),
			ionice_value=data.get("ionice_value"),
			stopped=data.get("stopped", False),
			create_time=data.get("create_time"),
			base_env=data.get("base_env"),
		)


@dataclass
class GroupInfo:
	name: str
	created_at: str
	env: dict[str, str] = field(default_factory=dict)
	env_file: str | None = None

	def to_dict(self) -> dict[str, Any]:
		return {
			"name": self.name,
			"created_at": self.created_at,
			"env": dict(self.env),
			"env_file": self.env_file,
		}

	@classmethod
	def from_dict(cls, data: dict[str, Any]) -> Self:
		return cls(
			name=data["name"],
			created_at=data["created_at"],
			env=data.get("env") or {},
			env_file=data.get("env_file"),
		)


@dataclass
class PortInfo:
	port: int
	name: str
	allocated_at: str

	def to_dict(self) -> dict[str, Any]:
		return {
			"port": self.port,
			"name": self.name,
			"allocated_at": self.allocated_at,
		}

	@classmethod
	def from_dict(cls, data: dict[str, Any]) -> Self:
		return cls(
			port=data["port"],
			name=data["name"],
			allocated_at=data["allocated_at"],
		)


@dataclass
class ProcessStatus:
	running: bool
	status: str
	cpu_percent: float
	memory_mb: float


@dataclass
class RemoteInfo:
	host: str
	user: str | None = None
	port: int | None = None
	created_at: str = ""
	batch_mode: bool = True

	def to_dict(self) -> dict[str, Any]:
		return {
			"host": self.host,
			"user": self.user,
			"port": self.port,
			"created_at": self.created_at,
			"batch_mode": self.batch_mode,
		}

	@classmethod
	def from_dict(cls, data: dict[str, Any]) -> Self:
		return cls(
			host=data["host"],
			user=data.get("user"),
			port=data.get("port"),
			created_at=data.get("created_at", ""),
			batch_mode=data.get("batch_mode", True),
		)
