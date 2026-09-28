"""Tests for StateStore and registry injection"""

from pathlib import Path

import pytest

from sentinel_core.models import ProcessInfo
from sentinel_core.state import State
from sentinel_core.state_store import StateStore, empty_state_data


class TestStateInjection:
	def test_state_dir_isolation(self, tmp_path: Path):
		state_dir = tmp_path / "sentinel-home"

		state = State(state_dir=state_dir)
		info = ProcessInfo(
			id=state.get_next_id(),
			pid=123,
			name="injected",
			cmd="sleep 10",
			cwd=str(tmp_path),
			restart=False,
			started_at="2024-01-01T00:00:00",
			stdout_log=str(state_dir / "logs" / "injected.stdout.log"),
			stderr_log=str(state_dir / "logs" / "injected.stderr.log"),
		)
		state.add_process(info)

		assert (state_dir / "state.json").exists()
		assert (state_dir / "logs").is_dir()

	def test_state_dir_shared_between_instances(self, tmp_path: Path):
		state_dir = tmp_path / "sentinel-home"

		first = State(state_dir=state_dir)
		info = ProcessInfo(
			id=first.get_next_id(),
			pid=123,
			name="shared",
			cmd="sleep 10",
			cwd=str(tmp_path),
			restart=False,
			started_at="2024-01-01T00:00:00",
			stdout_log="out.log",
			stderr_log="err.log",
		)
		first.add_process(info)

		second = State(state_dir=state_dir)
		assert second.find_process_by_name("shared") is not None
		assert second.next_id == 2

	def test_logs_dir_tracks_state_dir(self, tmp_path: Path):
		state_dir = tmp_path / "custom"

		state = State(state_dir=state_dir)

		assert state.logs_dir == state_dir / "logs"


class TestStateStore:
	def test_load_creates_directories(self, tmp_path: Path):
		state_dir = tmp_path / "fresh"

		store = StateStore(state_dir)
		store.load()

		assert state_dir.is_dir()
		assert (state_dir / "logs").is_dir()
		assert store.data == empty_state_data()

	def test_save_and_load_roundtrip(self, tmp_path: Path):
		store = StateStore(tmp_path)
		store.load()

		store.data["processes"]["1"] = {
			"id": 1,
			"pid": 42,
			"name": "roundtrip",
			"cmd": "true",
			"cwd": "/",
			"restart": False,
			"started_at": "2024-01-01T00:00:00",
			"stdout_log": "out.log",
			"stderr_log": "err.log",
		}
		store.save()

		reloaded = StateStore(tmp_path)
		reloaded.load()
		assert reloaded.data["processes"]["1"]["name"] == "roundtrip"

	@pytest.mark.parametrize(
		"raw",
		[
			"{not json at all",
			'{"processes": {"1": {"id": 1}}}',
		],
	)
	def test_load_resets_on_unparseable_data(self, tmp_path: Path, raw: str):
		state_file = tmp_path / "state.json"
		state_file.write_text(raw)

		store = StateStore(tmp_path)
		store.load()

		assert store.data == empty_state_data()
