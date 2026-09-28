"""Process and port state management"""

import os
from pathlib import Path

from .models import (
	GroupInfo,
	HealthCheckConfig,
	PortInfo,
	ProcessInfo,
	ProcessStatus,
	RemoteInfo,
)
from .registries import GroupRegistry, PortRegistry, ProcessRegistry, RemoteRegistry
from .state_store import StateStore

STATE_DIR: Path = Path(os.environ.get("SENTINEL_STATE_DIR", str(Path.home() / ".sentinel")))
STATE_FILE: Path = STATE_DIR / "state.json"
LOGS_DIR: Path = STATE_DIR / "logs"

__all__ = [
	"GroupInfo",
	"HealthCheckConfig",
	"PortInfo",
	"ProcessInfo",
	"ProcessStatus",
	"RemoteInfo",
	"State",
	"STATE_DIR",
	"STATE_FILE",
	"LOGS_DIR",
	"get_log_paths",
]


class State:
	"""Facade over the process, port, group, and remote registries."""

	def __init__(self, state_dir: Path | None = None) -> None:
		self.store = StateStore(state_dir if state_dir is not None else STATE_DIR)
		self.store.load()
		self._processes = ProcessRegistry(self.store)
		self._ports = PortRegistry(self.store)
		self._groups = GroupRegistry(self.store)
		self._remotes = RemoteRegistry(self.store)

	@property
	def processes(self) -> dict[int, ProcessInfo]:
		return self._processes.processes

	@property
	def ports(self) -> dict[int, PortInfo]:
		return self._ports.ports

	@property
	def groups(self) -> dict[str, GroupInfo]:
		return self._groups.groups

	@property
	def remotes(self) -> dict[str, RemoteInfo]:
		return self._remotes.remotes

	@property
	def next_id(self) -> int:
		return int(self.store.data.get("next_id", 1))

	@property
	def logs_dir(self) -> Path:
		return self.store.logs_dir

	@property
	def load_warnings(self) -> list[str]:
		return list(self.store.warnings)

	def save(self) -> None:
		self.store.save()

	# Process registry

	def get_next_id(self) -> int:
		return self._processes.get_next_id()

	def add_process(self, info: ProcessInfo) -> None:
		self._processes.add_process(info)

	def remove_process(self, id_: int) -> ProcessInfo | None:
		return self._processes.remove_process(id_)

	def get_process(self, id_: int) -> ProcessInfo | None:
		return self._processes.get(id_)

	def find_process_by_name(self, name: str) -> ProcessInfo | None:
		return self._processes.find_by_name(name)

	def list_processes(self) -> list[ProcessInfo]:
		return self._processes.all()

	# Port registry

	def allocate_port(self, name: str, port: int | None = None) -> int | None:
		return self._ports.allocate(name, port)

	def free_port(self, port: int) -> bool:
		return self._ports.free(port)

	def get_port(self, port: int) -> PortInfo | None:
		return self._ports.get(port)

	def list_ports(self, name: str | None = None) -> list[PortInfo]:
		"""Optionally filtered by name"""
		return self._ports.all(name)

	# Group registry

	def create_group(
		self, name: str, env: dict[str, str] | None = None, env_file: str | None = None
	) -> GroupInfo | None:
		return self._groups.create(name, env=env, env_file=env_file)

	def remove_group(self, name: str) -> bool:
		return self._groups.remove(name)

	def get_group(self, name: str) -> GroupInfo | None:
		return self._groups.get(name)

	def add_process_to_group(self, group_name: str, process_id: int) -> bool:
		return self._groups.add_process(group_name, process_id)

	def remove_process_from_group(self, process_id: int) -> bool:
		return self._groups.remove_process(process_id)

	def list_groups(self) -> list[GroupInfo]:
		return self._groups.all()

	def get_processes_in_group(self, group_name: str) -> list[ProcessInfo]:
		return self._groups.processes_in(group_name)

	# Remote registry

	def add_remote(self, info: RemoteInfo) -> RemoteInfo | None:
		return self._remotes.add(info)

	def remove_remote(self, host: str) -> bool:
		return self._remotes.remove(host)

	def get_remote(self, host: str) -> RemoteInfo | None:
		return self._remotes.get(host)

	def list_remotes(self) -> list[RemoteInfo]:
		return self._remotes.all()


def get_log_paths(name: str, logs_dir: Path | None = None) -> tuple[Path, Path]:
	base = logs_dir if logs_dir is not None else LOGS_DIR
	safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
	stdout = base / f"{safe_name}.stdout.log"
	stderr = base / f"{safe_name}.stderr.log"
	return stdout, stderr
