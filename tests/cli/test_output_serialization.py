import pytest
from typer.testing import CliRunner

from sentinel_cli import app
from sentinel_cli.startup import render_systemd_service

runner = CliRunner()


def test_regression_json_ignores_color_width_and_markup(state, spawn_process, monkeypatch) -> None:
	import json

	from rich.console import Console

	monkeypatch.setattr("sentinel_cli.metrics.console", Console(force_terminal=True, width=30))

	name = "[bold]" + "long-name-" * 12 + "[/bold]"
	spawn_process(name=name)
	monkeypatch.setenv("FORCE_COLOR", "1")
	monkeypatch.delenv("NO_COLOR", raising=False)
	monkeypatch.setenv("COLUMNS", "30")
	result = runner.invoke(app, ["metrics", "export", "-f", "json"])
	assert result.exit_code == 0
	assert "\x1b" not in result.stdout
	assert json.loads(result.stdout)[0]["name"] == name


def test_regression_systemd_output_is_not_terminal_formatted(monkeypatch) -> None:
	from rich.console import Console

	monkeypatch.setattr("sentinel_cli.startup.console", Console(force_terminal=True, width=25))
	monkeypatch.setenv("FORCE_COLOR", "1")
	monkeypatch.delenv("NO_COLOR", raising=False)
	monkeypatch.setenv("COLUMNS", "25")
	command = ["/bin/echo", "long value " * 30, "date +%s", "$HOME", 'a"b', "[bold]"]
	expected = render_systemd_service("[service]", command)
	result = runner.invoke(app, ["startup", "systemd", "--name", "[service]", "--", *command])
	assert result.exit_code == 0, result.output
	assert result.stdout == expected
	assert "\x1b" not in result.stdout
	assert "%%s" in result.stdout and "$$HOME" in result.stdout
	assert '\\"' in result.stdout
	assert sum(line.startswith("ExecStart=") for line in result.stdout.splitlines()) == 1
	assert "\\[" not in result.stdout


@pytest.mark.parametrize("field", ["name", "user", "cwd"])
def test_regression_systemd_rejects_directive_injection(field: str) -> None:
	options = {"name": "service", "user": "worker", "cwd": "/tmp"}
	options[field] += "\nExecStart=/bin/false"
	with pytest.raises(ValueError, match="newlines"):
		render_systemd_service(options["name"], ["/bin/true"], user=options["user"], cwd=options["cwd"])
