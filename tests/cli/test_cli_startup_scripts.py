"""Tests for startup script generation CLI commands"""

import pytest
from typer.testing import CliRunner

from sentinel_cli import app
from sentinel_cli.startup import _systemd_argument, render_systemd_service

runner = CliRunner()


@pytest.mark.parametrize(
	("value", "quoted"),
	[("", '""'), ("%", '"%%"'), ("$", '"$$"'), ("a\tb", '"a\tb"'), ("a'b", '"a\'b"')],
)
def test_systemd_argument_edge_cases(value: str, quoted: str) -> None:
	assert _systemd_argument(value) == quoted


def test_systemd_user_and_directory_escape_literal_percent() -> None:
	unit = render_systemd_service("literal", ["/bin/true"], user="%u", cwd="/tmp/a%b")
	assert "User=%%u\n" in unit
	assert "WorkingDirectory=/tmp/a%%b\n" in unit


class TestStartupCommands:
	def test_render_systemd_service_minimal(self) -> None:
		unit = render_systemd_service("myservice", ["python", "app.py"])
		assert "[Unit]" in unit
		assert "Description=Sentinel process: myservice" in unit
		assert "ExecStart=/usr/bin/env python app.py" in unit
		assert "Restart=no" in unit
		assert unit.endswith("\n")

	def test_render_systemd_service_with_user_cwd_restart(self) -> None:
		unit = render_systemd_service(
			"myservice",
			["python", "app.py", "--flag", "value with spaces"],
			user="deploy",
			cwd="/srv/app",
			restart=True,
		)
		assert "User=deploy" in unit
		assert "WorkingDirectory=/srv/app" in unit
		assert "Restart=always" in unit
		assert '"value with spaces"' in unit

	def test_startup_systemd_command(self) -> None:
		result = runner.invoke(app, ["startup", "systemd", "--name", "myservice", "python", "app.py"])
		assert result.exit_code == 0
		assert "[Unit]" in result.stdout
		assert "ExecStart=/usr/bin/env python app.py" in result.stdout

	def test_startup_systemd_rejects_empty_name(self) -> None:
		result = runner.invoke(app, ["startup", "systemd", "--name", "   ", "python", "app.py"])
		assert result.exit_code != 0
		assert "service name cannot be empty" in result.stdout.lower()
