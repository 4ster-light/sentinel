from pathlib import Path

from sentinel_core.state import State


def test_regression_new_logs_are_private(state, spawn_process) -> None:
	info = spawn_process(name="private-log")
	assert Path(info.stdout_log).stat().st_mode & 0o777 == 0o600
	assert Path(info.stderr_log).stat().st_mode & 0o777 == 0o600


def test_regression_new_state_directories_are_private(tmp_path: Path) -> None:
	state = State(state_dir=tmp_path / "private")
	assert state.store.state_dir.stat().st_mode & 0o777 == 0o700
	assert state.logs_dir.stat().st_mode & 0o777 == 0o700
