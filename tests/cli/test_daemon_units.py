"""Unit tests for the daemon internals that run in the child process"""

import os
import stat
from contextlib import contextmanager
from types import SimpleNamespace
from typing import ClassVar

import pytest

import sentinel_cli.daemon as daemon


class TestWriteDaemonPid:
	def test_writes_pid_and_removes_temporary_file(self, temp_state_dir: object) -> None:
		daemon._write_daemon_pid(4242)
		assert daemon.DAEMON_PID_FILE.read_text() == "4242"
		assert not daemon.DAEMON_PID_FILE.with_name("daemon.pid.tmp").exists()

	def test_creates_state_dir_with_owner_only_mode(
		self, temp_state_dir: object, monkeypatch: pytest.MonkeyPatch
	) -> None:
		state_dir = temp_state_dir / "nested" / "state"
		monkeypatch.setattr(daemon, "STATE_DIR", state_dir)
		monkeypatch.setattr(daemon, "DAEMON_PID_FILE", state_dir / "daemon.pid")
		daemon._write_daemon_pid(7)
		assert stat.S_IMODE(state_dir.stat().st_mode) == 0o700
		assert (state_dir / "daemon.pid").read_text() == "7"


class TestDaemonSubprocessEnv:
	def test_sets_the_state_dir(self, temp_state_dir: object, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setenv("SENTINEL_STATE_DIR", "/elsewhere")
		env = daemon._daemon_subprocess_env()
		assert env["SENTINEL_STATE_DIR"] == str(daemon.STATE_DIR)

	def test_keeps_the_rest_of_the_environment(self, temp_state_dir: object, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setenv("SENTINEL_TEST_MARKER", "1")
		env = daemon._daemon_subprocess_env()
		assert env["SENTINEL_TEST_MARKER"] == "1"

	def test_prepends_importable_paths_to_the_existing_pythonpath(
		self, temp_state_dir: object, monkeypatch: pytest.MonkeyPatch, tmp_path: object
	) -> None:
		site = tmp_path / "site"
		site.mkdir()
		monkeypatch.setattr(daemon.sys, "path", [str(site), "", "/nonexistent-sentinel", os.getcwd()])
		monkeypatch.setenv("PYTHONPATH", "/existing")
		env = daemon._daemon_subprocess_env()
		assert env["PYTHONPATH"] == os.pathsep.join([str(site), "/existing"])

	def test_sets_pythonpath_without_an_existing_value(
		self, temp_state_dir: object, monkeypatch: pytest.MonkeyPatch, tmp_path: object
	) -> None:
		site = tmp_path / "site"
		site.mkdir()
		monkeypatch.setattr(daemon.sys, "path", [str(site)])
		monkeypatch.delenv("PYTHONPATH", raising=False)
		env = daemon._daemon_subprocess_env()
		assert env["PYTHONPATH"] == str(site)

	def test_omits_pythonpath_without_importable_paths(
		self, temp_state_dir: object, monkeypatch: pytest.MonkeyPatch
	) -> None:
		monkeypatch.setattr(daemon.sys, "path", ["", os.getcwd(), "/nonexistent-sentinel"])
		monkeypatch.delenv("PYTHONPATH", raising=False)
		env = daemon._daemon_subprocess_env()
		assert "PYTHONPATH" not in env


class TestIsDaemonProcess:
	def test_matches_the_module_name(self, temp_state_dir: object, monkeypatch: pytest.MonkeyPatch) -> None:
		class FakeProcess:
			def __init__(self, pid: int) -> None:
				self.pid = pid

			def cmdline(self) -> list[str]:
				return ["/usr/bin/python", "-m", "sentinel_cli.daemon", "monitor"]

		monkeypatch.setattr(daemon.psutil, "Process", FakeProcess)
		assert daemon._is_daemon_process(10) is True

	def test_rejects_a_foreign_command_line(self, temp_state_dir: object, monkeypatch: pytest.MonkeyPatch) -> None:
		class FakeProcess:
			def __init__(self, pid: int) -> None:
				self.pid = pid

			def cmdline(self) -> list[str]:
				return ["/usr/bin/python", "script.py"]

		monkeypatch.setattr(daemon.psutil, "Process", FakeProcess)
		assert daemon._is_daemon_process(10) is False

	def test_rejects_a_process_that_disappeared(self, temp_state_dir: object, monkeypatch: pytest.MonkeyPatch) -> None:
		def missing(pid: int) -> object:
			raise daemon.psutil.NoSuchProcess(pid)

		monkeypatch.setattr(daemon.psutil, "Process", missing)
		assert daemon._is_daemon_process(10) is False


class TestDaemonLock:
	def test_rejects_a_second_non_blocking_holder(self, temp_state_dir: object) -> None:
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
		self.callbacks: dict[str, object] = {}
		self.started = False
		self.stopped = False
		FakeMonitor.instances.append(self)

	def set_restart_callback(self, callback: object) -> None:
		self.callbacks["restart"] = callback

	def set_scale_callback(self, callback: object) -> None:
		self.callbacks["scale"] = callback

	def start(self) -> None:
		self.started = True

	def stop(self) -> None:
		self.stopped = True


def _fake_signals(monkeypatch: pytest.MonkeyPatch) -> dict[int, object]:
	handlers: dict[int, object] = {}
	monkeypatch.setattr(daemon.signal, "signal", lambda signum, handler: handlers.__setitem__(signum, handler))
	return handlers


class TestRunMonitor:
	def test_runs_one_tick_and_cleans_up(
		self, temp_state_dir: object, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
	) -> None:
		caplog.set_level("INFO")
		handlers = _fake_signals(monkeypatch)
		monkeypatch.setattr(daemon, "_configure_daemon_logging", lambda: None)
		monkeypatch.setattr(daemon, "RestartMonitor", FakeMonitor)
		FakeMonitor.instances.clear()
		slept: list[float] = []

		def fake_sleep(seconds: float) -> None:
			slept.append(seconds)
			handlers[daemon.signal.SIGTERM](daemon.signal.SIGTERM, None)

		daemon._run_monitor(sleep=fake_sleep)

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

	def test_keeps_a_pid_file_from_another_process(
		self, temp_state_dir: object, monkeypatch: pytest.MonkeyPatch
	) -> None:
		handlers = _fake_signals(monkeypatch)
		monkeypatch.setattr(daemon, "_configure_daemon_logging", lambda: None)
		monkeypatch.setattr(daemon, "RestartMonitor", FakeMonitor)
		monkeypatch.setattr(daemon, "_write_daemon_pid", lambda pid: daemon.DAEMON_PID_FILE.write_text(str(pid + 1)))

		def fake_sleep(seconds: float) -> None:
			handlers[daemon.signal.SIGINT](daemon.signal.SIGINT, None)

		daemon._run_monitor(sleep=fake_sleep)
		assert daemon.DAEMON_PID_FILE.read_text() == str(os.getpid() + 1)


class TestDaemonMainLoop:
	def test_takes_the_exclusive_lock_then_runs_the_monitor(
		self, temp_state_dir: object, monkeypatch: pytest.MonkeyPatch
	) -> None:
		calls: list[object] = []

		@contextmanager
		def fake_lock(name: str, blocking: bool = True) -> object:
			calls.append((name, blocking))
			yield

		monkeypatch.setattr(daemon, "_daemon_lock", fake_lock)
		monkeypatch.setattr(daemon, "_run_monitor", lambda: calls.append("monitor"))
		daemon._daemon_main_loop()
		assert calls == [("daemon.lock", False), "monitor"]
