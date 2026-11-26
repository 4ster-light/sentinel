"""Tests for the State facade"""

from pathlib import Path

from sentinel_core.models import ProcessInfo, RemoteInfo
from sentinel_core.state import State, get_log_paths


def make_process(id_: int = 1, name: str = "api") -> ProcessInfo:
	return ProcessInfo(
		id=id_,
		pid=1000 + id_,
		name=name,
		cmd="true",
		cwd="/",
		restart=False,
		started_at="t",
		stdout_log="out.log",
		stderr_log="err.log",
	)


class TestState:
	def test_removes_process_from_group(self, tmp_path: Path) -> None:
		state = State(state_dir=tmp_path)

		assert state.remove_process_from_group(1) is False

	def test_removes_remote(self, tmp_path: Path) -> None:
		state = State(state_dir=tmp_path)
		state.add_remote(RemoteInfo(host="host"))

		assert state.remove_remote("host") is True
		assert state.remove_remote("host") is False

	def test_finds_process_by_id_name_and_numeric_string(self, tmp_path: Path) -> None:
		state = State(state_dir=tmp_path)
		state.add_process(make_process(1, "api"))

		assert state.find_process(1) is not None
		assert state.find_process("1") is not None
		assert state.find_process(" api ") is not None
		assert state.find_process("missing") is None

	def test_allocates_and_frees_ports(self, tmp_path: Path) -> None:
		state = State(state_dir=tmp_path)
		port = state.allocate_port("api", 4010)

		assert port == 4010
		info = state.get_port(4010)
		assert info is not None
		assert info.port == 4010
		assert info.name == "api"
		assert state.free_port(4010) is True

	def test_next_id_starts_at_one(self, tmp_path: Path) -> None:
		state = State(state_dir=tmp_path)

		assert state.next_id == 1


class TestLogPaths:
	def test_builds_paths_under_logs_dir(self, tmp_path: Path) -> None:
		stdout, stderr = get_log_paths("api", tmp_path)

		assert stdout == tmp_path / "api.stdout.log"
		assert stderr == tmp_path / "api.stderr.log"

	def test_quotes_unsafe_names(self, tmp_path: Path) -> None:
		stdout, _ = get_log_paths("a b/c", tmp_path)

		assert stdout == tmp_path / "a%20b%2Fc.stdout.log"
