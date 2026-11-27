"""Unit tests for the daemon internals that run in the child process"""

import logging
import os
import stat
import threading
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import Mock

import pytest

import sentinel_cli.daemon as daemon


class TestWriteDaemonPid:
	def test_writes_pid_and_removes_temporary_file(self, temp_state_dir: Path) -> None:
		daemon._write_daemon_pid(4242)
		assert daemon.DAEMON_PID_FILE.read_text() == "4242"
		assert not daemon.DAEMON_PID_FILE.with_name("daemon.pid.tmp").exists()

	def test_creates_state_dir_with_owner_only_mode(
		self, temp_state_dir: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		state_dir = temp_state_dir / "nested" / "state"
		monkeypatch.setattr(daemon, "STATE_DIR", state_dir)
		monkeypatch.setattr(daemon, "DAEMON_PID_FILE", state_dir / "daemon.pid")
		daemon._write_daemon_pid(7)
		assert stat.S_IMODE(state_dir.stat().st_mode) == 0o700
		assert (state_dir / "daemon.pid").read_text() == "7"


class TestDaemonSubprocessEnv:
	def test_sets_the_state_dir(self, temp_state_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setenv("SENTINEL_STATE_DIR", "/elsewhere")
		env = daemon._daemon_subprocess_env()
		assert env["SENTINEL_STATE_DIR"] == str(daemon.STATE_DIR)

	def test_keeps_the_rest_of_the_environment(self, temp_state_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setenv("SENTINEL_TEST_MARKER", "1")
		env = daemon._daemon_subprocess_env()
		assert env["SENTINEL_TEST_MARKER"] == "1"

	def test_drops_mutation_testing_markers(self, temp_state_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setenv("MUTANT_UNDER_TEST", "other.module.mutant")
		monkeypatch.setenv("MUTMUT_DEPENDENCY_DEPTH", "2")
		env = daemon._daemon_subprocess_env()
		assert "MUTANT_UNDER_TEST" not in env
		assert "MUTMUT_DEPENDENCY_DEPTH" not in env

	def test_prepends_importable_paths_to_the_existing_pythonpath(
		self, temp_state_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
	) -> None:
		site = tmp_path / "site"
		site.mkdir()
		monkeypatch.setattr(daemon.sys, "path", [str(site), "", "/nonexistent-sentinel", os.getcwd()])
		monkeypatch.setenv("PYTHONPATH", "/existing")
		env = daemon._daemon_subprocess_env()
		assert env["PYTHONPATH"] == os.pathsep.join([str(site), "/existing"])

	def test_sets_pythonpath_without_an_existing_value(
		self, temp_state_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
	) -> None:
		site = tmp_path / "site"
		site.mkdir()
		monkeypatch.setattr(daemon.sys, "path", [str(site)])
		monkeypatch.delenv("PYTHONPATH", raising=False)
		env = daemon._daemon_subprocess_env()
		assert env["PYTHONPATH"] == str(site)

	def test_omits_pythonpath_without_importable_paths(
		self, temp_state_dir: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		monkeypatch.setattr(daemon.sys, "path", ["", os.getcwd(), "/nonexistent-sentinel"])
		monkeypatch.delenv("PYTHONPATH", raising=False)
		env = daemon._daemon_subprocess_env()
		assert "PYTHONPATH" not in env


class TestIsDaemonProcess:
	def test_matches_the_module_name(self, temp_state_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		class FakeProcess:
			def __init__(self, pid: int) -> None:
				self.pid = pid

			def cmdline(self) -> list[str]:
				return ["/usr/bin/python", "-m", "sentinel_cli.daemon", "monitor"]

		monkeypatch.setattr(daemon.psutil, "Process", FakeProcess)
		assert daemon._is_daemon_process(10) is True

	def test_rejects_a_foreign_command_line(self, temp_state_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		class FakeProcess:
			def __init__(self, pid: int) -> None:
				self.pid = pid

			def cmdline(self) -> list[str]:
				return ["/usr/bin/python", "script.py"]

		monkeypatch.setattr(daemon.psutil, "Process", FakeProcess)
		assert daemon._is_daemon_process(10) is False

	def test_rejects_a_command_line_that_mentions_the_module_name(
		self, temp_state_dir: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		class FakeProcess:
			def __init__(self, pid: int) -> None:
				self.pid = pid

			def cmdline(self) -> list[str]:
				return ["/usr/bin/python", "/usr/bin/mutmut", "run", "sentinel_cli.daemon.*"]

		monkeypatch.setattr(daemon.psutil, "Process", FakeProcess)
		assert daemon._is_daemon_process(10) is False

	def test_rejects_a_process_that_disappeared(self, temp_state_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		def missing(pid: int) -> object:
			raise daemon.psutil.NoSuchProcess(pid)

		monkeypatch.setattr(daemon.psutil, "Process", missing)
		assert daemon._is_daemon_process(10) is False


class TestDaemonLock:
	def test_rejects_a_second_non_blocking_holder(self, temp_state_dir: Path) -> None:
		with (
			daemon._daemon_lock("daemon.lock", blocking=False),
			pytest.raises(BlockingIOError),
			daemon._daemon_lock("daemon.lock", blocking=False),
		):
			pass


class FakeMonitor:
	instances: ClassVar[list[FakeMonitor]] = []

	def __init__(self, check_interval: float) -> None:
		self.check_interval = check_interval
		self.callbacks: dict[str, Callable[..., None]] = {}
		self.started = False
		self.stopped = False
		FakeMonitor.instances.append(self)

	def set_restart_callback(self, callback: Callable[..., None]) -> None:
		self.callbacks["restart"] = callback

	def set_scale_callback(self, callback: Callable[..., None]) -> None:
		self.callbacks["scale"] = callback

	def start(self) -> None:
		self.started = True

	def stop(self) -> None:
		self.stopped = True


def _fake_signals(monkeypatch: pytest.MonkeyPatch) -> dict[int, Callable[..., None]]:
	handlers: dict[int, Callable[..., None]] = {}
	monkeypatch.setattr(daemon.signal, "signal", lambda signum, handler: handlers.__setitem__(signum, handler))
	return handlers


def _run_bounded(action: Callable[[], None], timeout: float = 5.0) -> None:
	thread = threading.Thread(target=action, daemon=True)
	thread.start()
	thread.join(timeout)
	assert not thread.is_alive(), "the call did not finish within the deadline"


class TestRunMonitor:
	def test_runs_one_tick_and_cleans_up(
		self, temp_state_dir: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
	) -> None:
		caplog.set_level("INFO")
		handlers = _fake_signals(monkeypatch)
		monkeypatch.setattr(daemon, "_configure_daemon_logging", lambda: None)
		monkeypatch.setattr(daemon, "RestartMonitor", FakeMonitor)
		FakeMonitor.instances.clear()
		slept: list[float] = []

		def fake_sleep(seconds: float) -> None:
			slept.append(seconds)
			assert len(slept) == 1, "the monitor loop must stop after the handler fires"
			handlers[daemon.signal.SIGTERM](daemon.signal.SIGTERM, None)

		_run_bounded(lambda: daemon._run_monitor(sleep=fake_sleep))

		monitor = FakeMonitor.instances[0]
		assert monitor.check_interval == 5.0
		assert slept == [1]
		assert monitor.started is True
		assert monitor.stopped is True
		assert set(handlers) == {daemon.signal.SIGTERM, daemon.signal.SIGINT}
		assert not daemon.DAEMON_PID_FILE.exists()
		assert f"Daemon started (pid: {os.getpid()})" in caplog.text
		assert "Daemon stopped" in caplog.text

		restart = monitor.callbacks["restart"]
		restart(SimpleNamespace(name="api", pid=1), SimpleNamespace(name="api", pid=2))
		assert "Restarted api (old_pid: 1, new_pid: 2)" in caplog.text
		scale = monitor.callbacks["scale"]
		scale("web", 1, 3)
		assert "Autoscaled cluster 'web' from 1 to 3 instance(s)" in caplog.text

	def test_keeps_a_pid_file_from_another_process(self, temp_state_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		handlers = _fake_signals(monkeypatch)
		monkeypatch.setattr(daemon, "_configure_daemon_logging", lambda: None)
		monkeypatch.setattr(daemon, "RestartMonitor", FakeMonitor)
		monkeypatch.setattr(daemon, "_write_daemon_pid", lambda pid: daemon.DAEMON_PID_FILE.write_text(str(pid + 1)))

		def fake_sleep(seconds: float) -> None:
			handlers[daemon.signal.SIGINT](daemon.signal.SIGINT, None)

		_run_bounded(lambda: daemon._run_monitor(sleep=fake_sleep))
		assert daemon.DAEMON_PID_FILE.read_text() == str(os.getpid() + 1)


class TestDaemonMainLoop:
	def test_takes_the_exclusive_lock_then_runs_the_monitor(
		self, temp_state_dir: Path, monkeypatch: pytest.MonkeyPatch
	) -> None:
		calls: list[object] = []

		@contextmanager
		def fake_lock(name: str, blocking: bool = True) -> Generator[None]:
			calls.append((name, blocking))
			yield

		monkeypatch.setattr(daemon, "_daemon_lock", fake_lock)
		monkeypatch.setattr(daemon, "_run_monitor", lambda: calls.append("monitor"))
		daemon._daemon_main_loop()
		assert calls == [("daemon.lock", False), "monitor"]


class TestConfigureDaemonLogging:
	def test_configures_a_rotating_handler(self, temp_state_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		configure = Mock()
		monkeypatch.setattr(daemon.logging, "basicConfig", configure)
		daemon._configure_daemon_logging()
		handler = configure.call_args.kwargs["handlers"][0]
		try:
			assert handler.baseFilename == str(daemon.STATE_DIR / "daemon.log")
			assert handler.maxBytes == daemon.DEFAULT_LOG_ROTATION_MAX_BYTES
			assert handler.backupCount == daemon.DEFAULT_LOG_ROTATION_BACKUPS
			assert handler.rotator is daemon._rotate_daemon_log
		finally:
			handler.close()
		assert configure.call_args.kwargs["level"] == logging.INFO
		assert configure.call_args.kwargs["format"] == "%(asctime)s %(levelname)s %(name)s: %(message)s"


class TestRotateDaemonLog:
	def test_copies_then_truncates_the_active_log(self, temp_state_dir: Path) -> None:
		source = daemon.STATE_DIR / "daemon.log"
		source.parent.mkdir(parents=True, exist_ok=True)
		source.write_text("line one\n")
		destination = daemon.STATE_DIR / "daemon.log.1"
		daemon._rotate_daemon_log(str(source), str(destination))
		assert destination.read_text() == "line one\n"
		assert source.read_text() == ""


class TestGetDaemonPid:
	def test_returns_a_live_daemon_pid(self, temp_state_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		import subprocess

		child = subprocess.Popen(["sleep", "30"])
		try:
			daemon.DAEMON_PID_FILE.write_text(str(child.pid))
			monkeypatch.setattr(daemon, "_is_daemon_process", lambda pid: True)

			assert daemon._get_daemon_pid() == child.pid
			with pytest.raises(subprocess.TimeoutExpired):
				child.wait(timeout=0.2)
		finally:
			child.kill()
			child.wait()


class TestDaemonSubprocessEnvEdges:
	def test_ignores_path_entries_that_are_not_directories(
		self, temp_state_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
	) -> None:
		module = tmp_path / "module.py"
		module.write_text("")
		monkeypatch.setattr(daemon.sys, "path", [str(module)])
		monkeypatch.delenv("PYTHONPATH", raising=False)
		env = daemon._daemon_subprocess_env()
		assert "PYTHONPATH" not in env

	def test_treats_an_empty_pythonpath_as_absent(
		self, temp_state_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
	) -> None:
		site = tmp_path / "site"
		site.mkdir()
		monkeypatch.setattr(daemon.sys, "path", [str(site)])
		monkeypatch.setenv("PYTHONPATH", "")
		env = daemon._daemon_subprocess_env()
		assert env["PYTHONPATH"] == str(site)
