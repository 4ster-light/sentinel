"""Tests for CLI main commands"""

import os

import pytest
from typer.testing import CliRunner

from sentinel_cli import app
from sentinel_cli.main import _parse_ionice_option
from sentinel_core.process import start_process
from sentinel_core.state import State

runner = CliRunner()


class TestMainCommands:
	"""Tests for main process commands"""

	def test_run_command_basic(self, state: State):
		"""Test basic run command"""
		result = runner.invoke(app, ["run", "echo", "test"])
		assert result.exit_code == 0
		assert "Started" in result.stdout

	def test_run_command_with_name(self, state: State):
		"""Test run command with name"""
		result = runner.invoke(app, ["run", "echo", "test", "--name", "myprocess"])
		assert result.exit_code == 0
		assert "myprocess" in result.stdout

	def test_run_command_with_group(self, state: State):
		"""Test run command with group that doesn't exist"""
		result = runner.invoke(app, ["run", "echo", "test", "--group", "nonexistent"])
		assert result.exit_code == 0
		assert "group" in result.stdout.lower() or "started" in result.stdout.lower()

	def test_run_command_with_restart(self, state: State):
		"""Test run command with restart flag"""
		result = runner.invoke(app, ["run", "echo", "test", "--name", "restart_test", "--restart"])
		assert result.exit_code == 0
		assert "Started" in result.stdout

	@pytest.mark.skipif(not hasattr(os, "geteuid"), reason="POSIX-only user switching")
	def test_run_command_with_user(self, state: State):
		result = runner.invoke(app, ["run", "sleep", "5", "--name", "user_cli_test", "--user", str(os.geteuid())])
		assert result.exit_code == 0
		reloaded_state = State()
		info = reloaded_state.find_process_by_name("user_cli_test")
		assert info is not None
		assert info.user is not None

	@pytest.mark.skipif(os.name == "nt", reason="POSIX-only user switching")
	def test_run_command_rejects_unknown_user(self, state: State):
		result = runner.invoke(app, ["run", "sleep", "5", "--name", "unknown_user", "--user", "__missing_user__"])
		assert result.exit_code != 0
		assert "not found" in result.stdout.lower()

	def test_run_command_rejects_empty_command(self, state: State):
		result = runner.invoke(app, ["run", "   ", "--name", "empty_cli_cmd"])
		assert result.exit_code != 0
		assert "cannot be empty" in result.stdout.lower()

	def test_run_command_with_cwd(self, state: State, tmp_path):
		"""Test run command with cwd option"""
		result = runner.invoke(app, ["run", "pwd", "--name", "cwd_test", "--cwd", str(tmp_path)])
		assert result.exit_code == 0
		assert "Started" in result.stdout

		reloaded_state = State()
		info = reloaded_state.find_process_by_name("cwd_test")
		assert info is not None
		assert info.cwd == str(tmp_path)

	def test_run_command_with_http_health_check(self, state: State):
		result = runner.invoke(
			app,
			[
				"run",
				"echo",
				"test",
				"--name",
				"health_http_test",
				"--health-http",
				"http://127.0.0.1:8080/health",
			],
		)
		assert result.exit_code == 0
		assert "Health checks are configured" in result.stdout

		reloaded_state = State()
		info = reloaded_state.find_process_by_name("health_http_test")
		assert info is not None
		assert info.health_check is not None
		assert info.health_check.kind == "http"
		assert info.health_check.target == "http://127.0.0.1:8080/health"

	def test_run_command_with_tcp_health_check(self, state: State):
		result = runner.invoke(
			app,
			[
				"run",
				"echo",
				"test",
				"--name",
				"health_tcp_test",
				"--health-tcp",
				"127.0.0.1:8080",
			],
		)
		assert result.exit_code == 0

		reloaded_state = State()
		info = reloaded_state.find_process_by_name("health_tcp_test")
		assert info is not None
		assert info.health_check is not None
		assert info.health_check.kind == "tcp"
		assert info.health_check.target == "127.0.0.1:8080"

	def test_run_command_rejects_multiple_health_check_types(self, state: State):
		result = runner.invoke(
			app,
			[
				"run",
				"echo",
				"test",
				"--health-http",
				"http://127.0.0.1:8080/health",
				"--health-tcp",
				"127.0.0.1:8080",
			],
		)
		assert result.exit_code != 0
		assert "Use only one" in result.stdout

	def test_run_command_rejects_invalid_health_failures(self, state: State):
		result = runner.invoke(
			app, ["run", "echo", "test", "--health-http", "http://127.0.0.1", "--health-failures", "0"]
		)
		assert result.exit_code != 0
		assert "--health-failures" in result.stdout

	def test_run_command_rejects_invalid_startup_timeout(self, state: State):
		result = runner.invoke(app, ["run", "sleep", "5", "--name", "sto_timeout_bad", "--startup-timeout", "0"])
		assert result.exit_code != 0
		assert "startup-timeout" in result.stdout

	def test_run_command_rejects_invalid_nice(self, state: State):
		result = runner.invoke(app, ["run", "sleep", "5", "--name", "nice_bad", "--nice", "99"])
		assert result.exit_code != 0
		assert "nice" in result.stdout.lower()

	def test_run_command_rejects_invalid_ionice(self, state: State):
		result = runner.invoke(app, ["run", "sleep", "5", "--name", "ionice_bad", "--ionice", "nope"])
		assert result.exit_code != 0

	def test_parse_ionice_option(self) -> None:
		assert _parse_ionice_option(None) == (None, None)
		assert _parse_ionice_option("idle") == ("idle", None)
		assert _parse_ionice_option("best-effort") == ("best_effort", None)
		assert _parse_ionice_option("best-effort:6") == ("best_effort", 6)
		with pytest.raises(ValueError):
			_parse_ionice_option("best-effort:99")

	def test_list_command_empty(self):
		"""Test list command with no processes"""
		result = runner.invoke(app, ["list"])
		assert result.exit_code == 0
		# Either shows no processes or an empty table
		assert "No processes" in result.stdout or "ID" in result.stdout
		if "ID" in result.stdout:
			assert "USER" in result.stdout

	def test_list_command_with_processes(self, state: State):
		"""Test list command with processes"""
		start_process(state, "echo test1", name="proc1")
		start_process(state, "echo test2", name="proc2")

		result = runner.invoke(app, ["list"])
		assert result.exit_code == 0
		assert "proc1" in result.stdout or "proc2" in result.stdout

	def test_stop_command(self, state: State):
		"""Test stopping a process"""
		info = start_process(state, "sleep 10", name="stoptest")
		result = runner.invoke(app, ["stop", str(info.id)])
		assert result.exit_code == 0
		assert "Stopped" in result.stdout

	def test_stop_command_by_name(self, state: State):
		"""Test stopping a process by name"""
		_ = start_process(state, "sleep 10", name="stoptest2")
		result = runner.invoke(app, ["stop", "stoptest2"])
		assert result.exit_code == 0
		assert "Stopped" in result.stdout

	def test_stop_command_force(self, state: State):
		"""Test stopping with force"""
		info = start_process(state, "sleep 10", name="forcestop")
		result = runner.invoke(app, ["stop", str(info.id), "--force"])
		assert result.exit_code == 0

	def test_stop_command_nonexistent(self):
		"""Test stopping nonexistent process fails"""
		result = runner.invoke(app, ["stop", "9999"])
		assert result.exit_code != 0

	def test_restart_command(self, state: State):
		"""Test restarting a process"""
		info = start_process(state, "echo test", name="restarttest")
		result = runner.invoke(app, ["restart", str(info.id)])
		assert result.exit_code == 0
		assert "Restarted" in result.stdout

	def test_restart_command_by_name(self, state: State):
		"""Test restarting a process by name"""
		_ = start_process(state, "echo test", name="restarttest2")
		result = runner.invoke(app, ["restart", "restarttest2"])
		assert result.exit_code == 0
		assert "Restarted" in result.stdout

	def test_restart_command_nonexistent(self):
		"""Test restarting nonexistent process fails"""
		result = runner.invoke(app, ["restart", "9999"])
		assert result.exit_code != 0

	def test_status_command(self, state: State):
		"""Test getting process status"""
		info = start_process(state, "sleep 10", name="statustest")
		result = runner.invoke(app, ["status", str(info.id)])
		assert result.exit_code == 0
		assert "statustest" in result.stdout
		assert "User:" in result.stdout

	def test_status_command_by_name(self, state: State):
		"""Test getting status by name"""
		_ = start_process(state, "sleep 10", name="statustest2")
		result = runner.invoke(app, ["status", "statustest2"])
		assert result.exit_code == 0
		assert "statustest2" in result.stdout

	def test_status_command_nonexistent(self):
		"""Test status of nonexistent process fails"""
		result = runner.invoke(app, ["status", "9999"])
		assert result.exit_code != 0

	def test_logs_command(self, state: State):
		"""Test viewing logs"""
		info = start_process(state, "echo test", name="logstest")
		result = runner.invoke(app, ["logs", str(info.id)])
		assert result.exit_code == 0

	def test_logs_command_by_name(self, state: State):
		"""Test viewing logs by name"""
		_ = start_process(state, "echo test", name="logstest2")
		result = runner.invoke(app, ["logs", "logstest2"])
		assert result.exit_code == 0

	def test_logs_command_clear(self, state: State):
		"""Test clearing logs"""
		info = start_process(state, "echo test", name="cleartest")
		result = runner.invoke(app, ["logs", str(info.id), "--clear"])
		assert result.exit_code == 0
		assert "Cleared" in result.stdout

	def test_logs_command_nonexistent(self):
		"""Test logs of nonexistent process fails"""
		result = runner.invoke(app, ["logs", "9999"])
		assert result.exit_code != 0

	def test_clean_command(self):
		"""Test clean command"""
		result = runner.invoke(app, ["clean"])
		assert result.exit_code == 0

	def test_startall_command_empty(self):
		"""Test startall with no processes"""
		result = runner.invoke(app, ["startall"])
		assert result.exit_code == 0

	def test_startall_command_with_processes(self, state: State):
		"""Test startall with processes"""
		_ = start_process(state, "echo test1", name="start1")
		_ = start_process(state, "echo test2", name="start2")

		# The processes are already running, just verify command works
		result = runner.invoke(app, ["startall"])
		assert result.exit_code == 0

	def test_restartall_command_empty(self):
		"""Test restartall with no processes"""
		result = runner.invoke(app, ["restartall"])
		assert result.exit_code == 0

	def test_restartall_command_with_processes(self, state: State):
		"""Test restartall with processes"""
		_ = start_process(state, "echo test1", name="restart1")
		_ = start_process(state, "echo test2", name="restart2")

		result = runner.invoke(app, ["restartall"])
		assert result.exit_code == 0

	def test_stopall_command(self, state: State):
		"""Test stopping all processes"""
		_ = start_process(state, "sleep 10", name="stopall1")
		_ = start_process(state, "sleep 10", name="stopall2")

		result = runner.invoke(app, ["stopall"])
		assert result.exit_code == 0

	def test_stopall_force(self, state: State):
		"""Test stopping all with force"""
		_ = start_process(state, "sleep 10", name="forcestopall1")
		result = runner.invoke(app, ["stopall", "--force"])
		assert result.exit_code == 0
