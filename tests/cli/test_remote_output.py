"""Value tests for the remote result printer"""

from io import StringIO

import pytest
import typer
from rich.console import Console

import sentinel_cli.remote as remote
from sentinel_core.remote import RemoteResult


def console_pair(monkeypatch: pytest.MonkeyPatch) -> tuple[StringIO, StringIO]:
	out = StringIO()
	err = StringIO()
	monkeypatch.setattr(remote, "console", Console(file=out, width=80, height=24))
	monkeypatch.setattr(remote, "error_console", Console(file=err, width=80, height=24))
	return out, err


def test_prints_stdout_and_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
	out, err = console_pair(monkeypatch)

	remote._print_remote_result(RemoteResult(returncode=0, stdout="hello\n", stderr="bad\n"))

	assert out.getvalue() == "hello\n"
	assert err.getvalue() == "bad\n"


def test_skips_empty_streams(monkeypatch: pytest.MonkeyPatch) -> None:
	out, err = console_pair(monkeypatch)

	remote._print_remote_result(RemoteResult(returncode=0, stdout="", stderr=""))

	assert out.getvalue() == ""
	assert err.getvalue() == ""


def test_zero_exit_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
	console_pair(monkeypatch)

	remote._print_remote_result(RemoteResult(returncode=0, stdout="done\n", stderr=""))


def test_nonzero_exit_raises_the_code(monkeypatch: pytest.MonkeyPatch) -> None:
	console_pair(monkeypatch)

	with pytest.raises(typer.Exit) as excinfo:
		remote._print_remote_result(RemoteResult(returncode=3, stdout="", stderr="bad\n"))

	assert excinfo.value.exit_code == 3


def terminal_pair(monkeypatch: pytest.MonkeyPatch) -> tuple[StringIO, StringIO]:
	out = StringIO()
	err = StringIO()
	monkeypatch.setattr(
		remote, "console", Console(file=out, width=80, height=24, force_terminal=True, color_system="standard")
	)
	monkeypatch.setattr(
		remote, "error_console", Console(file=err, width=80, height=24, force_terminal=True, color_system="standard")
	)
	return out, err


def test_stdout_is_not_highlighted(monkeypatch: pytest.MonkeyPatch) -> None:
	out, _ = terminal_pair(monkeypatch)

	remote._print_remote_result(RemoteResult(returncode=0, stdout="value 42\n", stderr=""))

	assert out.getvalue() == "value 42\n"


def test_stderr_carries_the_red_style(monkeypatch: pytest.MonkeyPatch) -> None:
	_, err = terminal_pair(monkeypatch)

	remote._print_remote_result(RemoteResult(returncode=0, stdout="", stderr="bad\n"))

	assert err.getvalue() == "\x1b[31mbad\n\x1b[0m"


def test_stderr_is_not_highlighted(monkeypatch: pytest.MonkeyPatch) -> None:
	_, err = terminal_pair(monkeypatch)

	remote._print_remote_result(RemoteResult(returncode=0, stdout="", stderr="value 42\n"))

	assert err.getvalue() == "\x1b[31mvalue 42\n\x1b[0m"
