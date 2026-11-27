"""Value tests for the state store and the domain registries"""

from pathlib import Path

import pytest

from sentinel_core import registries
from sentinel_core.models import ProcessInfo, RemoteInfo
from sentinel_core.state_store import StateStore, empty_state_data


def new_store(tmp_path: Path) -> StateStore:
	store = StateStore(tmp_path / "state")
	store.load()
	return store


def process(name: str = "api", ident: int = 1) -> ProcessInfo:
	return ProcessInfo(
		id=ident,
		pid=0,
		name=name,
		cmd="true",
		cwd="/",
		restart=False,
		started_at="",
		stdout_log="",
		stderr_log="",
	)


class TestStateStore:
	def test_empty_state_shape(self) -> None:
		assert empty_state_data() == {"next_id": 1, "processes": {}, "ports": {}, "groups": {}, "remotes": {}}

	def test_load_creates_the_directories(self, tmp_path: Path) -> None:
		store = new_store(tmp_path)

		assert store.state_dir.is_dir()
		assert store.logs_dir.is_dir()
		assert store.data == empty_state_data()

	def test_save_round_trips(self, tmp_path: Path) -> None:
		store = new_store(tmp_path)
		store.data["next_id"] = 5
		store.save()

		again = StateStore(store.state_dir)
		again.load()

		assert again.data["next_id"] == 5

	def test_save_rejects_an_external_change(self, tmp_path: Path) -> None:
		store = new_store(tmp_path)
		store.save()
		other = StateStore(store.state_dir)
		other.load()
		other.data["next_id"] = 9
		other.save()

		store.data["next_id"] = 7
		with pytest.raises(ValueError, match="State changed on disk; reload it before saving"):
			store.save()

	def test_mutation_persists(self, tmp_path: Path) -> None:
		store = new_store(tmp_path)

		with store.mutation() as data:
			data["next_id"] = 3

		again = StateStore(store.state_dir)
		again.load()
		assert again.data["next_id"] == 3

	def test_corrupt_state_is_backed_up(self, tmp_path: Path) -> None:
		store = new_store(tmp_path)
		store.state_file.write_text("{bad json")

		store.load()

		assert store.data == empty_state_data()
		assert len(store.warnings) == 1
		assert "is corrupt" in store.warnings[0]
		assert list(store.state_dir.glob("state.json.corrupt-*"))

	def test_parse_fills_missing_sections(self, tmp_path: Path) -> None:
		store = new_store(tmp_path)
		store.state_file.write_text('{"next_id": 4}')

		store.load()

		assert store.data["next_id"] == 4
		assert store.data["processes"] == {}

	def test_atomic_write_leaves_no_temp(self, tmp_path: Path) -> None:
		store = new_store(tmp_path)
		store.save()

		assert not list(store.state_dir.glob(".*.tmp"))


class TestProcessRegistry:
	def test_ids_increment(self, tmp_path: Path) -> None:
		registry = registries.ProcessRegistry(new_store(tmp_path))

		assert registry.get_next_id() == 1
		assert registry.get_next_id() == 2

	def test_add_get_and_remove(self, tmp_path: Path) -> None:
		registry = registries.ProcessRegistry(new_store(tmp_path))
		info = process()

		registry.add_process(info)

		assert registry.get(1) == info
		assert registry.find_by_name("api") == info
		assert registry.find_by_name("absent") is None
		assert registry.all() == [info]
		assert registry.remove_process(1) == info
		assert registry.get(1) is None
		assert registry.remove_process(1) is None


class TestPortRegistry:
	def test_allocates_a_specific_port(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(registries, "_is_port_available", lambda port: True)
		registry = registries.PortRegistry(new_store(tmp_path))

		assert registry.allocate("web", 40000) == 40000

		allocated = registry.get(40000)
		assert allocated is not None
		assert allocated.name == "web"
		assert registry.all("web") == [allocated]
		assert registry.all("other") == []
		assert registry.all() == [allocated]

	def test_rejects_a_taken_port(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(registries, "_is_port_available", lambda port: True)
		registry = registries.PortRegistry(new_store(tmp_path))
		registry.allocate("web", 40000)

		assert registry.allocate("db", 40000) is None

	def test_rejects_an_unavailable_port(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(registries, "_is_port_available", lambda port: False)
		registry = registries.PortRegistry(new_store(tmp_path))

		assert registry.allocate("web", 40000) is None
		assert registry.ports == {}

	def test_allocates_an_automatic_port(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(registries, "_find_available_port", lambda taken: 41000)
		registry = registries.PortRegistry(new_store(tmp_path))

		assert registry.allocate("web") == 41000
		assert registry.ports[41000].name == "web"

	def test_reports_an_exhausted_search(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(registries, "_find_available_port", lambda taken: None)
		registry = registries.PortRegistry(new_store(tmp_path))

		assert registry.allocate("web") is None

	def test_free(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(registries, "_is_port_available", lambda port: True)
		registry = registries.PortRegistry(new_store(tmp_path))
		registry.allocate("web", 40000)

		assert registry.free(40000) is True
		assert registry.free(40000) is False
		assert registry.get(40000) is None


class TestGroupRegistry:
	def test_create_and_duplicate(self, tmp_path: Path) -> None:
		registry = registries.GroupRegistry(new_store(tmp_path))

		group = registry.create("web", env={"A": "1"})

		assert group is not None
		assert group.name == "web"
		assert group.env == {"A": "1"}
		assert group.created_at
		assert registry.create("web") is None
		assert registry.get("web") == group
		assert registry.all() == [group]

	def test_env_file_is_resolved(self, tmp_path: Path) -> None:
		registry = registries.GroupRegistry(new_store(tmp_path))

		group = registry.create("web", env_file=str(tmp_path / "group.env"))

		assert group is not None
		assert group.env_file == str((tmp_path / "group.env").resolve())

	def test_remove_clears_the_process_group(self, tmp_path: Path) -> None:
		store = new_store(tmp_path)
		groups = registries.GroupRegistry(store)
		processes = registries.ProcessRegistry(store)
		processes.add_process(process())
		groups.create("web")
		groups.add_process("web", 1)

		assert [p.name for p in groups.processes_in("web")] == ["api"]
		assert groups.remove("web") is True
		assert groups.get("web") is None
		assert groups.remove("web") is False
		cleared = processes.get(1)
		assert cleared is not None
		assert cleared.group is None

	def test_add_process_checks_the_group_and_the_process(self, tmp_path: Path) -> None:
		registry = registries.GroupRegistry(new_store(tmp_path))

		assert registry.add_process("absent", 1) is False
		registry.create("web")
		assert registry.add_process("web", 99) is False

	def test_remove_process(self, tmp_path: Path) -> None:
		store = new_store(tmp_path)
		groups = registries.GroupRegistry(store)
		processes = registries.ProcessRegistry(store)
		processes.add_process(process())
		groups.create("web")
		groups.add_process("web", 1)

		assert groups.remove_process(1) is True
		assert groups.remove_process(99) is False


class TestRemoteRegistry:
	def test_add_sets_the_created_at(self, tmp_path: Path) -> None:
		registry = registries.RemoteRegistry(new_store(tmp_path))
		info = RemoteInfo(host="example.com")

		added = registry.add(info)

		assert added is info
		assert info.created_at
		assert registry.get("example.com") == info
		assert registry.all() == [info]
		assert registry.add(RemoteInfo(host="example.com")) is None

	def test_remove(self, tmp_path: Path) -> None:
		registry = registries.RemoteRegistry(new_store(tmp_path))
		registry.add(RemoteInfo(host="example.com"))

		assert registry.remove("example.com") is True
		assert registry.remove("example.com") is False


class TestPortHelpers:
	def test_range_bounds(self) -> None:
		assert registries._is_port_available(1023) is False
		assert registries._is_port_available(65536) is False

	def test_reports_a_bind_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
		class FakeSocket:
			def __enter__(self) -> FakeSocket:
				return self

			def __exit__(self, *args: object) -> bool:
				return False

			def bind(self, address: tuple[str, int]) -> None:
				raise OSError("busy")

		monkeypatch.setattr(registries.socket, "socket", lambda *args: FakeSocket())

		assert registries._is_port_available(40000) is False

	def test_find_skips_taken_ports(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(registries.random, "randint", lambda low, high: 40000)
		monkeypatch.setattr(registries, "_is_port_available", lambda port: True)

		assert registries._find_available_port({40000}) is None

	def test_find_returns_a_free_port(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(registries.random, "randint", lambda low, high: 40001)
		monkeypatch.setattr(registries, "_is_port_available", lambda port: True)

		assert registries._find_available_port(set()) == 40001
