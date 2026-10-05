from rich.text import Text
from typer.testing import CliRunner

from sentinel_cli import app
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
