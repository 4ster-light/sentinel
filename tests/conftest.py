"""Pytest configuration and shared fixtures"""

import os
import tempfile
import warnings
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from sentinel_core.models import ProcessInfo
from sentinel_core.state import State


@pytest.fixture
def temp_state_dir(monkeypatch: pytest.MonkeyPatch):
	"""Create a temporary state directory for testing"""
	with tempfile.TemporaryDirectory() as tmpdir:
		temp_path = Path(tmpdir)
		state_dir = temp_path / ".sentinel"
		logs_dir = state_dir / "logs"
		state_dir.mkdir(parents=True, exist_ok=True)
		logs_dir.mkdir(parents=True, exist_ok=True)

		# Patch the state module constants
		monkeypatch.setattr("sentinel_core.state.STATE_DIR", state_dir)
		monkeypatch.setattr("sentinel_core.state.STATE_FILE", state_dir / "state.json")
		monkeypatch.setattr("sentinel_core.state.LOGS_DIR", logs_dir)
		monkeypatch.setattr("sentinel_cli.daemon.STATE_DIR", state_dir)
		monkeypatch.setattr("sentinel_cli.daemon.DAEMON_PID_FILE", state_dir / "daemon.pid")

		yield temp_path


@pytest.fixture
def state(temp_state_dir: Path) -> State:
	"""Create a clean State instance for testing"""
	return State()


@pytest.fixture
def temp_logs_dir(tmp_path: Path) -> Path:
	"""Create a temporary logs directory for testing"""
	logs = tmp_path / "logs"
	logs.mkdir()
	return logs


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, temp_state_dir: Path) -> None:
	# Keep implicit .env files and terminal styling independent of the caller.
	monkeypatch.delenv("FORCE_COLOR", raising=False)
	home = tmp_path / "isolated-home"
	home.mkdir()
	monkeypatch.setenv("HOME", str(home))
	monkeypatch.setenv("SENTINEL_STATE_DIR", str(temp_state_dir / ".sentinel"))
	monkeypatch.chdir(tmp_path)


@pytest.fixture
def spawn_process(state: State) -> Iterator[Callable[..., ProcessInfo]]:
	import signal

	import psutil

	from sentinel_core.process import start_process

	started: list[ProcessInfo] = []

	def spawn(command: str = "sleep 60", **kwargs: Any) -> ProcessInfo:
		info = start_process(state, command, **kwargs)
		started.append(info)
		return info

	yield spawn

	for info in [*started, *State(state_dir=state.store.state_dir).list_processes()]:
		try:
			os.killpg(info.pid, signal.SIGKILL)
		except ProcessLookupError:
			pass
		except PermissionError as e:
			warnings.warn(
				f"Could not clean up process group {info.pid}: {e}",
				RuntimeWarning,
				stacklevel=1,
			)
		try:
			psutil.Process(info.pid).wait(timeout=1)
		except psutil.NoSuchProcess, psutil.TimeoutExpired:
			pass


@pytest.fixture
def wait_for() -> Callable[[Callable[[], object]], None]:
	import time

	def wait(condition: Callable[[], object]) -> None:
		deadline = time.monotonic() + 5
		while not condition():
			if time.monotonic() >= deadline:
				raise AssertionError("Condition did not become true within five seconds")
			time.sleep(0.02)

	return wait


def pytest_configure() -> None:
	# Rich caches color support when the CLI modules are imported during collection.
	os.environ.pop("FORCE_COLOR", None)
