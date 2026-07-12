import subprocess
from unittest.mock import patch


from sentinel_core.remote import (
	_build_ssh_command,
	format_remote,
	run_remote_command,
	run_remote_sentinel,
)
from sentinel_core.state import RemoteInfo


class TestBuildSshCommand:
	def test_basic_host(self):
		remote = RemoteInfo(host="example.com")
		assert _build_ssh_command(remote) == ["ssh", "example.com"]

	def test_with_user(self):
		remote = RemoteInfo(host="example.com", user="admin")
		assert _build_ssh_command(remote) == ["ssh", "admin@example.com"]

	def test_with_port(self):
		remote = RemoteInfo(host="example.com", port=2222)
		assert _build_ssh_command(remote) == ["ssh", "-p", "2222", "example.com"]

	def test_with_user_and_port(self):
		remote = RemoteInfo(host="example.com", user="admin", port=2222)
		assert _build_ssh_command(remote) == ["ssh", "-p", "2222", "admin@example.com"]


class TestRunRemoteCommand:
	def test_success(self):
		remote = RemoteInfo(host="example.com", user="admin")
		with patch("sentinel_core.remote.subprocess.run") as mock_run:
			mock_run.return_value.returncode = 0
			mock_run.return_value.stdout = "hello"
			mock_run.return_value.stderr = ""
			result = run_remote_command(remote, ["echo", "hello"])

		assert result.returncode == 0
		assert result.stdout == "hello"
		assert result.stderr == ""
		mock_run.assert_called_once_with(
			["ssh", "admin@example.com", "echo", "hello"],
			capture_output=True,
			text=True,
			check=False,
			timeout=10,
		)

	def test_ssh_not_found(self):
		remote = RemoteInfo(host="example.com")
		with patch("sentinel_core.remote.subprocess.run") as mock_run:
			mock_run.side_effect = FileNotFoundError("ssh")
			result = run_remote_command(remote, ["echo"])

		assert result.returncode == 127
		assert "ssh binary not found" in result.stderr

	def test_timeout(self):
		remote = RemoteInfo(host="example.com")
		with patch("sentinel_core.remote.subprocess.run") as mock_run:
			mock_run.side_effect = subprocess.TimeoutExpired(cmd="ssh", timeout=10)
			result = run_remote_command(remote, ["echo"])

		assert result.returncode == 124
		assert "timed out" in result.stderr

	def test_custom_timeout_forwarded(self):
		remote = RemoteInfo(host="example.com")
		with patch("sentinel_core.remote.subprocess.run") as mock_run:
			mock_run.return_value.returncode = 0
			mock_run.return_value.stdout = ""
			mock_run.return_value.stderr = ""
			run_remote_command(remote, ["echo"], timeout=30)

		mock_run.assert_called_once_with(
			["ssh", "example.com", "echo"],
			capture_output=True,
			text=True,
			check=False,
			timeout=30,
		)


class TestRunRemoteSentinel:
	def test_runs_sentinel_command(self):
		remote = RemoteInfo(host="example.com")
		with patch("sentinel_core.remote.subprocess.run") as mock_run:
			mock_run.return_value.returncode = 0
			mock_run.return_value.stdout = "ok"
			mock_run.return_value.stderr = ""
			result = run_remote_sentinel(remote, ["list"])

		assert result.returncode == 0
		assert result.stdout == "ok"
		mock_run.assert_called_once_with(
			["ssh", "example.com", "sentinel", "list"],
			capture_output=True,
			text=True,
			check=False,
			timeout=10,
		)


class TestFormatRemote:
	def test_host_only(self):
		assert format_remote(RemoteInfo(host="example.com")) == "example.com"

	def test_with_user(self):
		assert format_remote(RemoteInfo(host="example.com", user="admin")) == "admin@example.com"
