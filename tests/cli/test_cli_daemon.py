"""Tests for daemon CLI commands"""

import os
import time

from typer.testing import CliRunner

from sentinel_cli import app
import sentinel_cli.daemon as daemon

runner = CliRunner()


class TestDaemonCommands:
	def test_daemon_status_not_running(self) -> None:
		"""Test daemon status when not running"""
		daemon.DAEMON_PID_FILE.unlink(missing_ok=True)
		result = runner.invoke(app, ["daemon", "status"])
		assert result.exit_code == 0
		assert "not running" in result.stdout

	def test_daemon_stop_not_running(self) -> None:
		"""Test daemon stop when not running"""
		daemon.DAEMON_PID_FILE.unlink(missing_ok=True)
		result = runner.invoke(app, ["daemon", "stop"])
		assert result.exit_code == 0
		assert "not running" in result.stdout

	def test_get_daemon_pid_no_file(self) -> None:
		"""Test _get_daemon_pid when pid file doesn't exist"""
		daemon.DAEMON_PID_FILE.unlink(missing_ok=True)
		assert daemon._get_daemon_pid() is None

	def test_get_daemon_pid_invalid_content(self) -> None:
		"""Test _get_daemon_pid when pid file has invalid content"""
		daemon.DAEMON_PID_FILE.parent.mkdir(parents=True, exist_ok=True)
		daemon.DAEMON_PID_FILE.write_text("not_a_number")
		assert daemon._get_daemon_pid() is None
		assert not daemon.DAEMON_PID_FILE.exists()

	def test_get_daemon_pid_dead_process(self) -> None:
		"""Test _get_daemon_pid when pid file refers to dead process"""
		daemon.DAEMON_PID_FILE.parent.mkdir(parents=True, exist_ok=True)
		daemon.DAEMON_PID_FILE.write_text("999999")
		assert daemon._get_daemon_pid() is None
		assert not daemon.DAEMON_PID_FILE.exists()

	def test_is_daemon_running_not_running(self) -> None:
		"""Test is_daemon_running when daemon is not running"""
		daemon.DAEMON_PID_FILE.unlink(missing_ok=True)
		assert daemon.is_daemon_running() is False

	def test_daemon_start_and_stop(self) -> None:
		"""Test daemon start and stop lifecycle"""
		daemon.DAEMON_PID_FILE.unlink(missing_ok=True)

		result = runner.invoke(app, ["daemon", "start"])
		assert result.exit_code == 0
		assert "Started daemon" in result.stdout

		time.sleep(1.0)

		if daemon.DAEMON_PID_FILE.exists():
			pid = int(daemon.DAEMON_PID_FILE.read_text().strip())
			assert pid > 0

			result = runner.invoke(app, ["daemon", "status"])
			assert result.exit_code == 0
			assert "running" in result.stdout
			assert str(pid) in result.stdout

			result = runner.invoke(app, ["daemon", "start"])
			assert result.exit_code == 0
			assert "already running" in result.stdout

			result = runner.invoke(app, ["daemon", "stop"])
			assert result.exit_code == 0
			assert "Stopped daemon" in result.stdout

			for _ in range(20):
				time.sleep(0.2)
				try:
					os.kill(pid, 0)
				except OSError:
					break
			else:
				os.kill(pid, 9)

			result = runner.invoke(app, ["daemon", "status"])
			assert result.exit_code == 0
			assert "not running" in result.stdout
