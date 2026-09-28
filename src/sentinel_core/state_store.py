"""On-disk state storage"""

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

from .models import GroupInfo, PortInfo, ProcessInfo, RemoteInfo

STATE_FILENAME = "state.json"
LOGS_DIRNAME = "logs"


def empty_state_data() -> dict[str, Any]:
	return {"next_id": 1, "processes": {}, "ports": {}, "groups": {}, "remotes": {}}


def _validate_data(data: dict[str, Any]) -> None:
	"""Raise if any section entry cannot be parsed into its model."""
	{int(k): ProcessInfo.from_dict(v) for k, v in data["processes"].items()}
	{int(k): PortInfo.from_dict(v) for k, v in data["ports"].items()}
	{k: GroupInfo.from_dict(v) for k, v in data["groups"].items()}
	{k: RemoteInfo.from_dict(v) for k, v in data["remotes"].items()}


class StateStore:
	"""Owns the state.json file: parsing, writing, and the raw data dict."""

	def __init__(self, state_dir: Path) -> None:
		self.state_dir = state_dir
		self.state_file = state_dir / STATE_FILENAME
		self.logs_dir = state_dir / LOGS_DIRNAME
		self.data: dict[str, Any] = empty_state_data()
		self.warnings: list[str] = []

	def load(self) -> None:
		self.state_dir.mkdir(parents=True, exist_ok=True)
		self.logs_dir.mkdir(parents=True, exist_ok=True)
		if not self.state_file.exists():
			self.data = empty_state_data()
			return

		try:
			raw = json.loads(self.state_file.read_text())
			data = empty_state_data() | raw
			_validate_data(data)
		except json.JSONDecodeError, KeyError:
			data = empty_state_data()
		self.data = data

	def save(self) -> None:
		self.state_file.write_text(json.dumps(self.data, indent=2))

	@contextmanager
	def mutation(self) -> Generator[dict[str, Any], None, None]:
		"""Yield the data dict for modification, persisting it afterwards."""
		yield self.data
		self.save()
