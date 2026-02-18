"""Tests for CLI main commands"""

from typer.testing import CliRunner

from sentinel.cli import app
from sentinel.process import start_process
from sentinel.state import State

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

	def test_list_command_empty(self):
		"""Test list command with no processes"""
		result = runner.invoke(app, ["list"])
		assert result.exit_code == 0
		# Either shows no processes or an empty table
		assert "No processes" in result.stdout or "ID" in result.stdout

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
		info = start_process(state, "sleep 10", name="stoptest2")
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
		info = start_process(state, "echo test", name="restarttest2")
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

	def test_status_command_by_name(self, state: State):
		"""Test getting status by name"""
		info = start_process(state, "sleep 10", name="statustest2")
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
		info = start_process(state, "echo test", name="logstest2")
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
		info1 = start_process(state, "echo test1", name="start1")
		info2 = start_process(state, "echo test2", name="start2")

		# The processes are already running, just verify command works
		result = runner.invoke(app, ["startall"])
		assert result.exit_code == 0

	def test_restartall_command_empty(self):
		"""Test restartall with no processes"""
		result = runner.invoke(app, ["restartall"])
		assert result.exit_code == 0

	def test_restartall_command_with_processes(self, state: State):
		"""Test restartall with processes"""
		info1 = start_process(state, "echo test1", name="restart1")
		info2 = start_process(state, "echo test2", name="restart2")

		result = runner.invoke(app, ["restartall"])
		assert result.exit_code == 0

	def test_stopall_command(self, state: State):
		"""Test stopping all processes"""
		info1 = start_process(state, "sleep 10", name="stopall1")
		info2 = start_process(state, "sleep 10", name="stopall2")

		result = runner.invoke(app, ["stopall"])
		assert result.exit_code == 0

	def test_stopall_force(self, state: State):
		"""Test stopping all with force"""
		info1 = start_process(state, "sleep 10", name="forcestopall1")
		result = runner.invoke(app, ["stopall", "--force"])
		assert result.exit_code == 0
