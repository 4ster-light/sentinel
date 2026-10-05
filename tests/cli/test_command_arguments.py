import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from sentinel_cli import app
from sentinel_core.remote import _build_ssh_command, run_remote_command
from sentinel_core.state import RemoteInfo, State

runner = CliRunner()


def test_regression_run_preserves_argument_boundaries(state: State, spawn_process, tmp_path: Path, wait_for) -> None:
	import sys

	result = runner.invoke(app, ["run", "--name", "quoted", "--", sys.executable, "-c", "print('a b')"])
	assert result.exit_code == 0, result.output
	info = State().find_process_by_name("quoted")
	assert info is not None
	wait_for(lambda: Path(info.stdout_log).read_text() == "a b\n")
	assert Path(info.stderr_log).read_text() == ""


def test_regression_remote_arguments_survive_a_shell() -> None:
	import json
	import shlex
	import sys

	args = ["a b", "x; printf injected", "$(printf injected)", "a'b", "[bold]"]
	command = [sys.executable, "-c", "import json,sys; print(json.dumps(sys.argv[1:]))", *args]
	with patch("sentinel_core.remote.subprocess.run") as run:
		run_remote_command(RemoteInfo(host="example.com"), command)
		remote_script = run.call_args.args[0][-1]
	result = subprocess.run(["/bin/sh", "-c", remote_script], capture_output=True, text=True, check=True)
	assert json.loads(result.stdout) == args
	assert shlex.split(remote_script) == command


def test_regression_ssh_host_cannot_add_options() -> None:
	remote = RemoteInfo(host="-oProxyCommand=printf injected")
	command = _build_ssh_command(remote)
	assert command[-2:] == ["--", remote.host]
	assert "BatchMode=yes" in command


def test_remote_run_keeps_command_options(state: State, monkeypatch) -> None:
	from sentinel_core.remote import RemoteResult

	state.add_remote(RemoteInfo(host="remotehost"))
	with patch("sentinel_cli.remote.run_remote_sentinel", return_value=RemoteResult(0, "", "")) as remote:
		result = runner.invoke(app, ["remote", "run", "remotehost", "--", "python", "-c", "print('a b')"])
	assert result.exit_code == 0, result.output
	assert remote.call_args.args[1] == ["run", "--", "python", "-c", "print('a b')"]


def test_remote_output_is_literal(state: State) -> None:
	from sentinel_core.remote import RemoteResult

	state.add_remote(RemoteInfo(host="remotehost"))
	with patch(
		"sentinel_cli.remote.run_remote_sentinel",
		return_value=RemoteResult(0, "[/tmp/data] loaded\n", "[bold]literal[/bold]\n"),
	):
		result = runner.invoke(app, ["remote", "list", "remotehost"])
	assert result.exit_code == 0, result.exception
	assert "[/tmp/data] loaded" in result.stdout
	assert "[bold]literal[/bold]" in result.stderr


@pytest.mark.parametrize("filename", ["server with spaces", "server$literal"])
def test_run_single_executable_is_literal(state: State, spawn_process, tmp_path: Path, wait_for, filename: str) -> None:
	executable = tmp_path / filename
	executable.write_text("#!/bin/sh\nprintf 'ready\\n'\nsleep 60\n")
	executable.chmod(0o755)
	result = runner.invoke(app, ["run", "--", str(executable)])
	assert result.exit_code == 0, result.output
	info = State().find_process_by_name(filename)
	assert info is not None
	wait_for(lambda: Path(info.stdout_log).read_text() == "ready\n")
	assert Path(info.stderr_log).read_text() == ""


def test_run_shell_requires_an_explicit_flag(state: State, spawn_process, wait_for) -> None:
	result = runner.invoke(app, ["run", "--shell", "--", "printf 'ready\\n' && sleep 60"])
	assert result.exit_code == 0, result.output
	info = State().find_process_by_name("printf")
	assert info is not None
	wait_for(lambda: Path(info.stdout_log).read_text() == "ready\n")
	assert "--shell" in runner.invoke(app, ["run", "--help"]).stdout


def test_run_shell_rejects_multiple_arguments(state: State) -> None:
	result = runner.invoke(app, ["run", "--shell", "echo", "hello"])
	assert result.exit_code == 1
	assert result.stdout == ""
	assert "--shell requires one command string" in result.stderr
	assert state.list_processes() == []


def test_shell_cluster_names_use_the_executable(state: State, spawn_process, wait_for) -> None:
	result = runner.invoke(
		app,
		["run", "--shell", "--instances", "2", "--", "printf 'ready\\n' && sleep 60"],
	)
	assert result.exit_code == 0, result.output
	assert [info.name for info in State().list_processes()] == ["printf-1", "printf-2"]


def test_remote_run_joins_the_complete_command(state: State) -> None:
	import shlex

	state.add_remote(RemoteInfo(host="remotehost"))
	arguments = ["python", "-c", "print('a b')", "$(echo injected)", "x; echo injected"]
	with patch("sentinel_core.remote.subprocess.run") as run:
		run.return_value = subprocess.CompletedProcess([], 0, "", "")
		result = runner.invoke(app, ["remote", "run", "remotehost", "--", *arguments])
	assert result.exit_code == 0, result.output
	assert run.call_args.args[0][-1] == shlex.join(["sentinel", "run", "--", *arguments])


def test_remote_shell_flag_is_forwarded(state: State) -> None:
	from sentinel_core.remote import RemoteResult

	state.add_remote(RemoteInfo(host="remotehost"))
	with patch("sentinel_cli.remote.run_remote_sentinel", return_value=RemoteResult(0, "", "")) as remote:
		result = runner.invoke(
			app,
			["remote", "run", "--shell", "remotehost", "--", "echo ready && sleep 60"],
		)
	assert result.exit_code == 0, result.output
	assert remote.call_args.args[1] == [
		"run",
		"--shell",
		"--",
		"echo ready && sleep 60",
	]


def test_remote_stop_protects_option_like_names(state: State) -> None:
	from sentinel_core.remote import RemoteResult

	state.add_remote(RemoteInfo(host="remotehost"))
	with patch("sentinel_cli.remote.run_remote_sentinel", return_value=RemoteResult(0, "", "")) as remote:
		result = runner.invoke(app, ["remote", "stop", "remotehost", "--", "-worker"])
	assert result.exit_code == 0, result.output
	assert remote.call_args.args[1] == ["stop", "--", "-worker"]


def test_remote_interactive_mode_is_saved(state: State) -> None:
	result = runner.invoke(app, ["remote", "add", "example.com", "--interactive"])
	assert result.exit_code == 0, result.output
	remote = State().get_remote("example.com")
	assert remote is not None
	assert not remote.batch_mode
	assert _build_ssh_command(remote) == [
		"ssh",
		"-o",
		"BatchMode=no",
		"--",
		"example.com",
	]
	assert RemoteInfo.from_dict({"host": "legacy.example.com"}).batch_mode


@pytest.mark.parametrize(
	"arguments",
	[
		["stop", "missing"],
		["remote", "list", "missing"],
		["port", "free", "65535"],
		["metrics", "export", "-f", "bad"],
	],
)
def test_command_errors_go_to_stderr(state: State, arguments: list[str]) -> None:
	result = runner.invoke(app, arguments)
	assert result.exit_code == 1
	assert result.stdout == ""
	assert "✗" in result.stderr
