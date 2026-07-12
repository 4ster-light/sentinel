"""Tests for CLI remote commands"""

from unittest.mock import patch

from typer.testing import CliRunner

from sentinel_cli import app
from sentinel_core.remote import RemoteResult
from sentinel_core.state import RemoteInfo, State

runner = CliRunner()


class TestRemoteCommands:
	def test_remote_add(self, state: State):
		result = runner.invoke(app, ["remote", "add", "server1"])
		assert result.exit_code == 0
		assert "server1" in result.stdout
		reloaded = State()
		assert reloaded.get_remote("server1") is not None

	def test_remote_add_with_user_and_port(self, state: State):
		result = runner.invoke(app, ["remote", "add", "server2", "--user", "admin", "--port", "2222"])
		assert result.exit_code == 0
		reloaded = State()
		remote = reloaded.get_remote("server2")
		assert remote is not None
		assert remote.user == "admin"
		assert remote.port == 2222

	def test_remote_add_duplicate(self, state: State):
		state.add_remote(RemoteInfo(host="dup"))
		result = runner.invoke(app, ["remote", "add", "dup"])
		assert result.exit_code != 0

	def test_remote_remove(self, state: State):
		state.add_remote(RemoteInfo(host="toremove"))
		result = runner.invoke(app, ["remote", "remove", "toremove"])
		assert result.exit_code == 0
		reloaded = State()
		assert reloaded.get_remote("toremove") is None

	def test_remote_remove_nonexistent(self, state: State):
		result = runner.invoke(app, ["remote", "remove", "missing"])
		assert result.exit_code != 0

	def test_remote_list_empty(self, state: State):
		result = runner.invoke(app, ["remote", "list"])
		assert result.exit_code == 0
		assert "No remote hosts" in result.stdout

	def test_remote_list_with_hosts(self, state: State):
		state.add_remote(RemoteInfo(host="alpha", user="root", port=22))
		state.add_remote(RemoteInfo(host="beta"))
		result = runner.invoke(app, ["remote", "list"])
		assert result.exit_code == 0
		assert "alpha" in result.stdout
		assert "beta" in result.stdout

	def test_remote_list_host_command(self, state: State):
		state.add_remote(RemoteInfo(host="remotehost"))
		with patch("sentinel_cli.remote.run_remote_sentinel") as mock_run:
			mock_run.return_value = RemoteResult(returncode=0, stdout="remote output\n", stderr="")
			result = runner.invoke(app, ["remote", "list", "remotehost"])
		assert result.exit_code == 0
		assert "remote output" in result.stdout

	def test_remote_list_host_unknown(self, state: State):
		result = runner.invoke(app, ["remote", "list", "unknown"])
		assert result.exit_code != 0

	def test_remote_list_host_failure(self, state: State):
		state.add_remote(RemoteInfo(host="remotehost"))
		with patch("sentinel_cli.remote.run_remote_sentinel") as mock_run:
			mock_run.return_value = RemoteResult(returncode=1, stdout="", stderr="failed\n")
			result = runner.invoke(app, ["remote", "list", "remotehost"])
		assert result.exit_code == 1

	def test_remote_run_command(self, state: State):
		state.add_remote(RemoteInfo(host="remotehost"))
		with patch("sentinel_cli.remote.run_remote_sentinel") as mock_run:
			mock_run.return_value = RemoteResult(returncode=0, stdout="started\n", stderr="")
			result = runner.invoke(app, ["remote", "run", "remotehost", "sleep", "10"])
		assert result.exit_code == 0
		assert "started" in result.stdout
		mock_run.assert_called_once_with(
			state.get_remote("remotehost"),
			["run", "sleep", "10"],
		)

	def test_remote_run_unknown_host(self, state: State):
		result = runner.invoke(app, ["remote", "run", "unknown", "sleep", "10"])
		assert result.exit_code != 0

	def test_remote_stop_command(self, state: State):
		state.add_remote(RemoteInfo(host="remotehost"))
		with patch("sentinel_cli.remote.run_remote_sentinel") as mock_run:
			mock_run.return_value = RemoteResult(returncode=0, stdout="stopped\n", stderr="")
			result = runner.invoke(app, ["remote", "stop", "remotehost", "myproc"])
		assert result.exit_code == 0
		assert "stopped" in result.stdout
		mock_run.assert_called_once_with(
			state.get_remote("remotehost"),
			["stop", "myproc"],
		)

	def test_remote_stop_unknown_host(self, state: State):
		result = runner.invoke(app, ["remote", "stop", "unknown", "myproc"])
		assert result.exit_code != 0

	def test_remote_command_propagates_failure(self, state: State):
		state.add_remote(RemoteInfo(host="remotehost"))
		with patch("sentinel_cli.remote.run_remote_sentinel") as mock_run:
			mock_run.return_value = RemoteResult(returncode=1, stdout="", stderr="error\n")
			result = runner.invoke(app, ["remote", "run", "remotehost", "bad"])
		assert result.exit_code == 1

	def test_remote_list_host_stderr(self, state: State):
		state.add_remote(RemoteInfo(host="remotehost"))
		with patch("sentinel_cli.remote.run_remote_sentinel") as mock_run:
			mock_run.return_value = RemoteResult(returncode=0, stdout="", stderr="warning\n")
			result = runner.invoke(app, ["remote", "list", "remotehost"])
		assert result.exit_code == 0
		assert "warning" in result.stdout

	def test_remote_stop_stderr(self, state: State):
		state.add_remote(RemoteInfo(host="remotehost"))
		with patch("sentinel_cli.remote.run_remote_sentinel") as mock_run:
			mock_run.return_value = RemoteResult(returncode=0, stdout="stopped\n", stderr="warn\n")
			result = runner.invoke(app, ["remote", "stop", "remotehost", "myproc"])
		assert result.exit_code == 0
		assert "warn" in result.stdout

	def test_remote_stop_failure(self, state: State):
		state.add_remote(RemoteInfo(host="remotehost"))
		with patch("sentinel_cli.remote.run_remote_sentinel") as mock_run:
			mock_run.return_value = RemoteResult(returncode=1, stdout="", stderr="error\n")
			result = runner.invoke(app, ["remote", "stop", "remotehost", "myproc"])
		assert result.exit_code == 1
