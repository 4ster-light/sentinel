import pytest
from rich.text import Text
from typer.testing import CliRunner
from sentinel_cli import app
from sentinel_cli.startup import render_systemd_service
from sentinel_core.state import State

runner = CliRunner()


def test_regression_markup_names_remain_literal(state: State, spawn_process, monkeypatch) -> None:
	monkeypatch.setenv("COLUMNS", "240")
	name = "[/tmp/data]"
	state.create_group(name)
	info = spawn_process(name=name)
	state.add_process_to_group(name, info.id)
	for args in [["list"], ["status", str(info.id)], ["group", "list"], ["group", "list", name]]:
		result = runner.invoke(app, args)
		assert result.exit_code == 0, result.exception
		assert name in Text.from_ansi(result.stdout).plain


def test_regression_json_ignores_color_width_and_markup(state, spawn_process, monkeypatch) -> None:
	import json

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
