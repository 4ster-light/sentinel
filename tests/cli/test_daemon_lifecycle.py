import subprocess
import sys
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

import sentinel_cli.daemon as daemon
from sentinel_cli import app
from sentinel_core.restart_monitor import RestartMonitor

runner = CliRunner()


def test_daemon_rotation_keeps_stderr_in_the_current_log(temp_state_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
	import logging
	from unittest.mock import Mock

	configure = Mock()
	monkeypatch.setattr(daemon.logging, "basicConfig", configure)
	monkeypatch.setattr(daemon, "DEFAULT_LOG_ROTATION_MAX_BYTES", 1)
	path = temp_state_dir / ".sentinel" / "daemon.log"
	path.parent.mkdir(exist_ok=True)
	with path.open("a") as stderr:
		stderr.write("old data\n")
		stderr.flush()
		inode = path.stat().st_ino
		daemon._configure_daemon_logging()
		handler = configure.call_args.kwargs["handlers"][0]
		try:
			handler.emit(logging.LogRecord("daemon", logging.INFO, __file__, 0, "rotation trigger", (), None))
			stderr.write("startup traceback\n")
			stderr.flush()
		finally:
			handler.close()
	assert path.stat().st_ino == inode
	assert "rotation trigger\nstartup traceback\n" in path.read_text()
	assert path.with_name("daemon.log.1").read_text() == "old data\n"


def test_regression_concurrent_daemon_start_has_one_monitor(temp_state_dir: Path) -> None:
	import subprocess
	from concurrent.futures import ThreadPoolExecutor

	import psutil

	def invoke_start() -> subprocess.CompletedProcess[str]:
		return subprocess.run(
			[sys.executable, "-m", "sentinel_cli.daemon", "start"], text=True, capture_output=True, timeout=15
		)

	try:
		with ThreadPoolExecutor(max_workers=2) as pool:
			results = list(pool.map(lambda _: invoke_start(), range(2)))
		assert all(result.returncode == 0 for result in results)
		assert sum("Started daemon" in result.stdout for result in results) == 1
		assert sum("already running" in result.stdout for result in results) == 1
		pid = daemon._get_daemon_pid()
		assert pid is not None
		result = runner.invoke(app, ["daemon", "stop"])
		assert result.exit_code == 0
		assert not psutil.pid_exists(pid) or psutil.Process(pid).status() == psutil.STATUS_ZOMBIE
	finally:
		for proc in psutil.process_iter(["cmdline"]):
			try:
				if "sentinel_cli.daemon" in (proc.info["cmdline"] or []) and proc.environ().get(
					"SENTINEL_STATE_DIR"
				) == str(temp_state_dir / ".sentinel"):
					proc.kill()
					proc.wait(timeout=2)
			except psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired:
				pass


def test_regression_daemon_initialization_failure_is_reported(temp_state_dir: Path) -> None:
	log = temp_state_dir / ".sentinel" / "daemon.log"
	log.mkdir()
	result = runner.invoke(app, ["daemon", "start"])
	assert result.exit_code == 1
	assert "Failed to start daemon" in result.stdout
	assert daemon._get_daemon_pid() is None


def test_regression_monitor_sleep_is_interruptible() -> None:
	monitor = RestartMonitor(check_interval=60)
	monitor.start()
	started = time.monotonic()
	monitor.stop()
	assert time.monotonic() - started < 2
	assert monitor._thread is not None
	assert not monitor._thread.is_alive()
