"""Tests for StateStore and registry injection"""

import threading
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


class TestCorruptionGuard:
	def test_corrupt_file_backed_up_and_warned(self, tmp_path: Path):
		state_file = tmp_path / "state.json"
		state_file.write_text("{this is not json")

		store = StateStore(tmp_path)
		store.load()

		assert store.data == empty_state_data()
		assert len(store.warnings) == 1
		assert "corrupt" in store.warnings[0]

		backups = list(tmp_path.glob("state.json.corrupt-*"))
		assert len(backups) == 1
		assert backups[0].read_text() == "{this is not json"

	def test_malformed_entry_backed_up_and_warned(self, tmp_path: Path):
		state_file = tmp_path / "state.json"
		state_file.write_text('{"processes": {"1": {"id": 1}}}')

		store = StateStore(tmp_path)
		store.load()

		assert store.data == empty_state_data()
		assert store.warnings
		assert list(tmp_path.glob("state.json.corrupt-*"))

	def test_null_sections_treated_as_corrupt(self, tmp_path: Path):
		state_file = tmp_path / "state.json"
		state_file.write_text('{"processes": null}')

		store = StateStore(tmp_path)
		store.load()

		assert store.data == empty_state_data()
		assert store.warnings

	def test_valid_state_produces_no_warnings(self, tmp_path: Path):
		state_file = tmp_path / "state.json"
		state_file.write_text('{"next_id": 2, "processes": {}}')

		store = StateStore(tmp_path)
		store.load()

		assert store.warnings == []
		assert store.data["next_id"] == 2

	def test_state_facade_exposes_load_warnings(self, tmp_path: Path):
		(tmp_path / "state.json").write_text("[1, 2, 3]")

		state = State(state_dir=tmp_path)

		assert state.processes == {}
		assert len(state.load_warnings) == 1


class TestAtomicWrites:
	def test_save_leaves_no_temp_files(self, tmp_path: Path):
		store = StateStore(tmp_path)
		store.load()
		store.save()

		assert not list(tmp_path.glob("*.tmp"))
		assert store.state_file.exists()

	def test_failed_write_preserves_previous_content(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
		import json

		store = StateStore(tmp_path)
		store.load()
		store.data["next_id"] = 7
		store.save()
		assert json.loads(store.state_file.read_text())["next_id"] == 7

		def broken_dump(*args, **kwargs):
			raise OSError("disk on fire")

		monkeypatch.setattr("sentinel_core.state_store.json.dump", broken_dump)
		store.data["next_id"] = 99

		with pytest.raises(OSError, match="disk on fire"):
			store.save()

		assert json.loads(store.state_file.read_text())["next_id"] == 7
		assert not list(tmp_path.glob("*.tmp"))


class TestLockedMutations:
	def _make_process_entry(self, id_: int) -> dict[str, object]:
		return {
			"id": id_,
			"pid": 1000 + id_,
			"name": f"proc-{id_}",
			"cmd": "sleep 10",
			"cwd": "/",
			"restart": False,
			"started_at": "2024-01-01T00:00:00",
			"stdout_log": "out.log",
			"stderr_log": "err.log",
		}

	def test_mutation_reloads_concurrent_changes(self, tmp_path: Path):
		first = StateStore(tmp_path)
		first.load()
		second = StateStore(tmp_path)
		second.load()

		with second.mutation() as data:
			data["processes"]["1"] = self._make_process_entry(1)

		with first.mutation() as data:
			data["processes"]["2"] = self._make_process_entry(2)

		reloaded = StateStore(tmp_path)
		reloaded.load()
		assert set(reloaded.data["processes"]) == {"1", "2"}

	def test_concurrent_mutations_do_not_lose_updates(self, tmp_path: Path):
		threads = 4
		adds_per_thread = 5

		def add_entries(offset: int) -> None:
			store = StateStore(tmp_path)
			store.load()
			for i in range(adds_per_thread):
				with store.mutation() as data:
					data["processes"][str(offset + i)] = self._make_process_entry(offset + i)

		workers = [threading.Thread(target=add_entries, args=(offset * adds_per_thread,)) for offset in range(threads)]
		for worker in workers:
			worker.start()
		for worker in workers:
			worker.join()

		store = StateStore(tmp_path)
		store.load()
		assert len(store.data["processes"]) == threads * adds_per_thread

	def test_mutation_creates_lock_file(self, tmp_path: Path):
		store = StateStore(tmp_path)
		store.load()

		with store.mutation() as data:
			data["next_id"] = 2

		assert (tmp_path / "state.json.lock").exists()
