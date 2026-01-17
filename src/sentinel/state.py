"""Process and port state management"""

import json
import random
import socket
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

STATE_DIR: Path = Path.home() / ".sentinel"
STATE_FILE: Path = STATE_DIR / "state.json"
LOGS_DIR: Path = STATE_DIR / "logs"

MIN_PORT = 1024
MAX_PORT = 65535


@dataclass
class ProcessInfo:
	"""Information about a managed process"""

	id: int
	pid: int
	name: str
	cmd: str
	cwd: str
	restart: bool
	started_at: str
	stdout_log: str
	stderr_log: str
	env: dict[str, str] = field(default_factory=dict)
	group: str | None = None
	env_file: str | None = None

	def to_dict(self) -> dict[str, Any]:
		return {
			"id": self.id,
			"pid": self.pid,
			"name": self.name,
			"cmd": self.cmd,
			"cwd": self.cwd,
			"restart": self.restart,
			"started_at": self.started_at,
			"stdout_log": self.stdout_log,
			"stderr_log": self.stderr_log,
			"env": self.env,
			"group": self.group,
			"env_file": self.env_file,
		}

	@classmethod
	def from_dict(cls, data: dict[str, Any]) -> ProcessInfo:
		return cls(
			id=data["id"],
			pid=data["pid"],
			name=data["name"],
			cmd=data["cmd"],
			cwd=data["cwd"],
			restart=data["restart"],
			started_at=data["started_at"],
			stdout_log=data["stdout_log"],
			stderr_log=data["stderr_log"],
			env=data.get("env", {}),
			group=data.get("group"),
			env_file=data.get("env_file"),
		)


@dataclass
class GroupInfo:
	"""Information about a process group"""

	name: str
	created_at: str
	env: dict[str, str] = field(default_factory=dict)
	env_file: str | None = None

	def to_dict(self) -> dict[str, Any]:
		return {
			"name": self.name,
			"created_at": self.created_at,
			"env": self.env,
			"env_file": self.env_file,
		}

	@classmethod
	def from_dict(cls, data: dict[str, Any]) -> GroupInfo:
		return cls(
			name=data["name"],
			created_at=data["created_at"],
			env=data.get("env", {}),
			env_file=data.get("env_file"),
		)


@dataclass
class PortInfo:
	"""Information about an allocated port"""

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
	def from_dict(cls, data: dict[str, Any]) -> PortInfo:
		return cls(
			port=data["port"],
			name=data["name"],
			allocated_at=data["allocated_at"],
		)


class State:
	"""Manages process and port state"""

	def __init__(self) -> None:
		STATE_DIR.mkdir(parents=True, exist_ok=True)
		LOGS_DIR.mkdir(parents=True, exist_ok=True)
		self.processes: dict[int, ProcessInfo] = {}
		self.ports: dict[int, PortInfo] = {}
		self.groups: dict[str, GroupInfo] = {}
		self.next_id: int = 1
		self._load()

	def _load(self) -> None:
		"""Load state from disk"""
		if STATE_FILE.exists():
			try:
				data = json.loads(STATE_FILE.read_text())
				self.next_id = data.get("next_id", 1)
				self.processes = {int(k): ProcessInfo.from_dict(v) for k, v in data.get("processes", {}).items()}
				self.ports = {int(k): PortInfo.from_dict(v) for k, v in data.get("ports", {}).items()}
				self.groups = {k: GroupInfo.from_dict(v) for k, v in data.get("groups", {}).items()}
			except (json.JSONDecodeError, KeyError):
				pass

	def save(self) -> None:
		"""Save state to disk"""
		data = {
			"next_id": self.next_id,
			"processes": {k: v.to_dict() for k, v in self.processes.items()},
			"ports": {k: v.to_dict() for k, v in self.ports.items()},
			"groups": {k: v.to_dict() for k, v in self.groups.items()},
		}
		STATE_FILE.write_text(json.dumps(data, indent=2))

	def get_next_id(self) -> int:
		"""Get the next process ID"""
		id_ = self.next_id
		self.next_id += 1
		self.save()
		return id_

	def add_process(self, info: ProcessInfo) -> None:
		"""Add a process to state"""
		self.processes[info.id] = info
		self.save()

	def remove_process(self, id_: int) -> ProcessInfo | None:
		"""Remove a process from state"""
		info = self.processes.pop(id_, None)
		if info:
			self.save()
		return info

	def get_process(self, id_: int) -> ProcessInfo | None:
		"""Get a process by ID"""
		return self.processes.get(id_)

	def find_process_by_name(self, name: str) -> ProcessInfo | None:
		"""Find a process by name"""
		for info in self.processes.values():
			if info.name == name:
				return info
		return None

	def list_processes(self) -> list[ProcessInfo]:
		"""List all processes"""
		return list(self.processes.values())

	def allocate_port(self, name: str, port: int | None = None) -> int | None:
		"""Allocate a port"""
		if port is not None:
			if port in self.ports or not _is_port_available(port):
				return None
			allocated = port
		else:
			allocated = _find_available_port(set(self.ports.keys()))
			if allocated is None:
				return None

		self.ports[allocated] = PortInfo(
			port=allocated,
			name=name,
			allocated_at=datetime.now().isoformat(),
		)
		self.save()
		return allocated

	def free_port(self, port: int) -> bool:
		"""Free a port"""
		if port in self.ports:
			del self.ports[port]
			self.save()
			return True
		return False

	def get_port(self, port: int) -> PortInfo | None:
		"""Get port info"""
		return self.ports.get(port)

	def list_ports(self, name: str | None = None) -> list[PortInfo]:
		"""List ports, optionally filtered by name"""
		ports = list(self.ports.values())
		if name:
			ports = [p for p in ports if p.name == name]
		return ports

	def create_group(
		self, name: str, env: dict[str, str] | None = None, env_file: str | None = None
	) -> GroupInfo | None:
		"""Create a new group"""
		if name in self.groups:
			return None
		group = GroupInfo(
			name=name,
			created_at=datetime.now().isoformat(),
			env=env or {},
			env_file=env_file,
		)
		self.groups[name] = group
		self.save()
		return group

	def remove_group(self, name: str) -> bool:
		"""Delete a group and unassign all processes"""
		if name not in self.groups:
			return False
		del self.groups[name]
		# Unassign all processes from this group
		for info in self.processes.values():
			if info.group == name:
				info.group = None
		self.save()
		return True

	def get_group(self, name: str) -> GroupInfo | None:
		"""Get group by name"""
		return self.groups.get(name)

	def add_process_to_group(self, group_name: str, process_id: int) -> bool:
		"""Add (or move) a process to a group"""
		if group_name not in self.groups:
			return False
		if process_id not in self.processes:
			return False
		self.processes[process_id].group = group_name
		self.save()
		return True

	def remove_process_from_group(self, process_id: int) -> bool:
		"""Remove process from its group (if any)"""
		if process_id not in self.processes:
			return False
		self.processes[process_id].group = None
		self.save()
		return True

	def list_groups(self) -> list[GroupInfo]:
		"""List all groups"""
		return list(self.groups.values())

	def get_processes_in_group(self, group_name: str) -> list[ProcessInfo]:
		"""Get all processes in a specific group"""
		return [info for info in self.processes.values() if info.group == group_name]


def _is_port_available(port: int) -> bool:
	"""Check if a port is available"""
	if not MIN_PORT <= port <= MAX_PORT:
		return False
	with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
		try:
			s.bind(("127.0.0.1", port))
			return True
		except OSError:
			return False


def _find_available_port(allocated: set[int]) -> int | None:
	"""Find an available port"""
	for _ in range(100):
		port = random.randint(MIN_PORT, MAX_PORT)
		if port not in allocated and _is_port_available(port):
			return port
	return None


def get_log_paths(name: str) -> tuple[Path, Path]:
	"""Get log file paths for a process"""
	safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
	stdout = LOGS_DIR / f"{safe_name}.stdout.log"
	stderr = LOGS_DIR / f"{safe_name}.stderr.log"
	return stdout, stderr
