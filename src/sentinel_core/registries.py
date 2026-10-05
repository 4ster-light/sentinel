"""Domain registries over the shared state store"""

import random
import socket
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import GroupInfo, PortInfo, ProcessInfo, RemoteInfo
from .state_store import StateStore

MIN_PORT = 1024
MAX_PORT = 65535


def _now_isoformat() -> str:
	return datetime.now().isoformat()


def _is_port_available(port: int) -> bool:
	if not MIN_PORT <= port <= MAX_PORT:
		return False
	with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
		try:
			s.bind(("127.0.0.1", port))
			return True
		except OSError:
			return False


def _find_available_port(allocated: set[int]) -> int | None:
	for _ in range(100):
		port = random.randint(MIN_PORT, MAX_PORT)
		if port not in allocated and _is_port_available(port):
			return port
	return None


class ProcessRegistry:
	def __init__(self, store: StateStore) -> None:
		self._store = store

	@property
	def processes(self) -> dict[int, ProcessInfo]:
		entries = self._store.data.get("processes", {})
		return {int(k): ProcessInfo.from_dict(v) for k, v in entries.items()}

	def get_next_id(self) -> int:
		with self._store.mutation() as data:
			id_ = int(data.get("next_id", 1))
			data["next_id"] = id_ + 1
		return id_

	def add_process(self, info: ProcessInfo) -> None:
		with self._store.mutation() as data:
			data.setdefault("processes", {})[str(info.id)] = info.to_dict()

	def remove_process(self, id_: int) -> ProcessInfo | None:
		with self._store.mutation() as data:
			entry = data.get("processes", {}).pop(str(id_), None)
		return ProcessInfo.from_dict(entry) if entry else None

	def get(self, id_: int) -> ProcessInfo | None:
		entry = self._store.data.get("processes", {}).get(str(id_))
		return ProcessInfo.from_dict(entry) if entry else None

	def find_by_name(self, name: str) -> ProcessInfo | None:
		for info in self.processes.values():
			if info.name == name:
				return info
		return None

	def all(self) -> list[ProcessInfo]:
		return list(self.processes.values())


class PortRegistry:
	def __init__(self, store: StateStore) -> None:
		self._store = store

	@property
	def ports(self) -> dict[int, PortInfo]:
		entries = self._store.data.get("ports", {})
		return {int(k): PortInfo.from_dict(v) for k, v in entries.items()}

	def allocate(self, name: str, port: int | None = None) -> int | None:
		with self._store.mutation() as data:
			sections: dict[str, dict[str, Any]] = data.setdefault("ports", {})
			taken = {int(k) for k in sections}

			if port is not None:
				if port in taken or not _is_port_available(port):
					return None
				allocated = port
			else:
				allocated = _find_available_port(taken)
				if allocated is None:
					return None

			sections[str(allocated)] = PortInfo(
				port=allocated,
				name=name,
				allocated_at=_now_isoformat(),
			).to_dict()
		return allocated

	def free(self, port: int) -> bool:
		with self._store.mutation() as data:
			if str(port) not in data.get("ports", {}):
				return False
			del data["ports"][str(port)]
		return True

	def get(self, port: int) -> PortInfo | None:
		entry = self._store.data.get("ports", {}).get(str(port))
		return PortInfo.from_dict(entry) if entry else None

	def all(self, name: str | None = None) -> list[PortInfo]:
		ports = list(self.ports.values())
		if name:
			ports = [p for p in ports if p.name == name]
		return ports


class GroupRegistry:
	def __init__(self, store: StateStore) -> None:
		self._store = store

	@property
	def groups(self) -> dict[str, GroupInfo]:
		entries = self._store.data.get("groups", {})
		return {k: GroupInfo.from_dict(v) for k, v in entries.items()}

	def create(self, name: str, env: dict[str, str] | None = None, env_file: str | None = None) -> GroupInfo | None:
		with self._store.mutation() as data:
			if name in data.get("groups", {}):
				return None
			group = GroupInfo(
				name=name,
				created_at=_now_isoformat(),
				env=env or {},
				env_file=str(Path(env_file).resolve()) if env_file else None,
			)
			data.setdefault("groups", {})[name] = group.to_dict()
		return group

	def remove(self, name: str) -> bool:
		with self._store.mutation() as data:
			if name not in data.get("groups", {}):
				return False
			del data["groups"][name]

			for entry in data.get("processes", {}).values():
				if entry.get("group") == name:
					entry["group"] = None
		return True

	def get(self, name: str) -> GroupInfo | None:
		entry = self._store.data.get("groups", {}).get(name)
		return GroupInfo.from_dict(entry) if entry else None

	def add_process(self, group_name: str, process_id: int) -> bool:
		with self._store.mutation() as data:
			if group_name not in data.get("groups", {}):
				return False
			entry = data.get("processes", {}).get(str(process_id))
			if entry is None:
				return False
			entry["group"] = group_name
		return True

	def remove_process(self, process_id: int) -> bool:
		with self._store.mutation() as data:
			entry = data.get("processes", {}).get(str(process_id))
			if entry is None:
				return False
			entry["group"] = None
		return True

	def all(self) -> list[GroupInfo]:
		return list(self.groups.values())

	def processes_in(self, group_name: str) -> list[ProcessInfo]:
		entries = self._store.data.get("processes", {}).values()
		return [ProcessInfo.from_dict(entry) for entry in entries if entry.get("group") == group_name]


class RemoteRegistry:
	def __init__(self, store: StateStore) -> None:
		self._store = store

	@property
	def remotes(self) -> dict[str, RemoteInfo]:
		entries = self._store.data.get("remotes", {})
		return {k: RemoteInfo.from_dict(v) for k, v in entries.items()}

	def add(self, info: RemoteInfo) -> RemoteInfo | None:
		with self._store.mutation() as data:
			if info.host in data.get("remotes", {}):
				return None
			if not info.created_at:
				info.created_at = _now_isoformat()
			data.setdefault("remotes", {})[info.host] = info.to_dict()
		return info

	def remove(self, host: str) -> bool:
		with self._store.mutation() as data:
			if host not in data.get("remotes", {}):
				return False
			del data["remotes"][host]
		return True

	def get(self, host: str) -> RemoteInfo | None:
		entry = self._store.data.get("remotes", {}).get(host)
		return RemoteInfo.from_dict(entry) if entry else None

	def all(self) -> list[RemoteInfo]:
		return list(self.remotes.values())
