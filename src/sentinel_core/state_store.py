"""On-disk state storage"""

import json
import logging
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Generator

from .models import GroupInfo, PortInfo, ProcessInfo, RemoteInfo

STATE_FILENAME = "state.json"
LOCK_FILENAME = "state.json.lock"
LOGS_DIRNAME = "logs"

logger = logging.getLogger(__name__)


def empty_state_data() -> dict[str, Any]:
	return {"next_id": 1, "processes": {}, "ports": {}, "groups": {}, "remotes": {}}


def _validate_data(data: dict[str, Any]) -> None:
	"""Raise if any section entry cannot be parsed into its model."""
	int(data["next_id"])
	{int(k): ProcessInfo.from_dict(v) for k, v in data["processes"].items()}
	{int(k): PortInfo.from_dict(v) for k, v in data["ports"].items()}
	{k: GroupInfo.from_dict(v) for k, v in data["groups"].items()}
	{k: RemoteInfo.from_dict(v) for k, v in data["remotes"].items()}


class StateStore:
	"""Owns the state.json file: parsing, locking, atomic writes, and the raw data dict."""

	def __init__(self, state_dir: Path) -> None:
		self.state_dir = state_dir
		self.state_file = state_dir / STATE_FILENAME
		self.lock_file = state_dir / LOCK_FILENAME
		self.logs_dir = state_dir / LOGS_DIRNAME
		self.data: dict[str, Any] = empty_state_data()
		self.warnings: list[str] = []

	def load(self) -> None:
		self.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
		self.logs_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
		self.warnings = []
		if not self.state_file.exists():
			self.data = empty_state_data()
			return
		self.data = self._read_guarded()

	def save(self) -> None:
		"""Atomically write the current in-memory data."""
		self._atomic_write(self.data)

	@contextmanager
	def mutation(self) -> Generator[dict[str, Any], None, None]:
		"""Yield the data dict for modification, persisting it atomically.

		Holds the state lock for the whole read-modify-write cycle: the data dict
		is reloaded from disk before the caller mutates it, so concurrent
		writers cannot silently lose each other's changes.
		"""
		with self._lock():
			self.data = self._read_guarded() if self.state_file.exists() else empty_state_data()
			yield self.data
			self._atomic_write(self.data)

	def _read_guarded(self) -> dict[str, Any]:
		"""Read and validate state.json, backing up and warning on corruption."""
		try:
			raw = json.loads(self.state_file.read_text())
			data = empty_state_data() | raw
			_validate_data(data)
			return data
		except (json.JSONDecodeError, KeyError, TypeError, ValueError, AttributeError) as e:
			backup = self._backup_corrupt_file()
			message = f"state file {self.state_file} is corrupt ({type(e).__name__}: {e}); starting from empty state"
			if backup:
				message += f"; original backed up to {backup}"
			self.warnings.append(message)
			logger.warning(message)
			return empty_state_data()

	def _backup_corrupt_file(self) -> Path | None:
		timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
		backup = self.state_file.with_name(f"{self.state_file.name}.corrupt-{timestamp}")
		try:
			self.state_file.replace(backup)
		except OSError as e:
			logger.error(f"Failed to back up corrupt state file {self.state_file}: {e}")
			return None
		return backup

	def _atomic_write(self, data: dict[str, Any]) -> None:
		self.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
		fd, tmp_name = tempfile.mkstemp(dir=self.state_dir, prefix=f".{STATE_FILENAME}.", suffix=".tmp")
		try:
			with os.fdopen(fd, "w") as tmp_file:
				json.dump(data, tmp_file, indent=2)
				tmp_file.flush()
				os.fsync(tmp_file.fileno())
			os.replace(tmp_name, self.state_file)
		except BaseException:
			try:
				os.unlink(tmp_name)
			except OSError:
				pass
			raise

	@contextmanager
	def _lock(self) -> Generator[None, None, None]:
		try:
			import fcntl
		except ImportError:
			yield
			return
		with open(self.lock_file, "w") as lock_file:
			fcntl.flock(lock_file, fcntl.LOCK_EX)
			try:
				yield
			finally:
				fcntl.flock(lock_file, fcntl.LOCK_UN)
