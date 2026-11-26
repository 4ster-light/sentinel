"""Tests for the remote transport helpers"""

import subprocess

import pytest

from sentinel_core import remote
from sentinel_core.models import RemoteInfo


class TestBuildSshCommand:
	def test_batch_mode_without_user_or_port(self) -> None:
		assert remote._build_ssh_command(RemoteInfo(host="host")) == [
			"ssh",
			"-o",
			"BatchMode=yes",
			"--",
			"host",
		]

	def test_interactive_with_port_and_user(self) -> None:
		command = remote._build_ssh_command(RemoteInfo(host="host", user="alice", port=2222, batch_mode=False))

		assert command == ["ssh", "-o", "BatchMode=no", "-p", "2222", "--", "alice@host"]


class TestRunRemoteCommand:
	def test_returns_streams_and_returncode(self, monkeypatch: pytest.MonkeyPatch) -> None:
		seen: list[list[str]] = []

		def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
			seen.append(cmd)
			return subprocess.CompletedProcess(cmd, 3, "out", "err")

		monkeypatch.setattr(subprocess, "run", fake_run)

		result = remote.run_remote_command(RemoteInfo(host="host"), ["echo", "hi"], timeout=7)

		assert result == remote.RemoteResult(returncode=3, stdout="out", stderr="err")
		assert seen == [["ssh", "-o", "BatchMode=yes", "--", "host", "echo hi"]]

	def test_reports_missing_ssh(self, monkeypatch: pytest.MonkeyPatch) -> None:
		def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
			raise FileNotFoundError("ssh")

		monkeypatch.setattr(subprocess, "run", fake_run)

		result = remote.run_remote_command(RemoteInfo(host="host"), ["true"])

		assert result.returncode == 127
		assert result.stdout == ""
		assert "ssh binary not found" in result.stderr

	def test_reports_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
		def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
			raise subprocess.TimeoutExpired(cmd, 10)

		monkeypatch.setattr(subprocess, "run", fake_run)

		result = remote.run_remote_command(RemoteInfo(host="host"), ["true"], timeout=5)

		assert result.returncode == 124
		assert result.stderr == "SSH connection to host timed out after 5s"

	def test_sentinel_wrapper_prefixes_argv(self, monkeypatch: pytest.MonkeyPatch) -> None:
		seen: list[list[str]] = []

		def fake_run_remote(remote_info: RemoteInfo, args: list[str], timeout: int = 10) -> remote.RemoteResult:
			seen.append([remote_info.host, *args, str(timeout)])
			return remote.RemoteResult(0, "", "")

		monkeypatch.setattr(remote, "run_remote_command", fake_run_remote)

		remote.run_remote_sentinel(RemoteInfo(host="host"), ["ls", "-l"], timeout=4)

		assert seen == [["host", "sentinel", "ls", "-l", "4"]]


class TestFormatRemote:
	def test_with_user(self) -> None:
		assert remote.format_remote(RemoteInfo(host="host", user="alice")) == "alice@host"

	def test_without_user(self) -> None:
		assert remote.format_remote(RemoteInfo(host="host")) == "host"
