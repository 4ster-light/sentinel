from rich.console import Console
from rich.text import Text
from typer.testing import CliRunner

import sentinel_cli.group
import sentinel_cli.main
from sentinel_cli import app
from sentinel_core.state import State

runner = CliRunner()


def test_regression_markup_names_remain_literal(state: State, spawn_process, monkeypatch) -> None:
	# xdist exports COLUMNS=80 in workers and Console() snapshots it at import time,
	# so the module consoles are replaced with fixed-width ones instead of an environment override.
	monkeypatch.setattr(sentinel_cli.main, "console", Console(width=240, height=25))
	monkeypatch.setattr(sentinel_cli.group, "console", Console(width=240, height=25))
	name = "[/tmp/data]"
	state.create_group(name)
	info = spawn_process(name=name)
	state.add_process_to_group(name, info.id)
	for args in [["list"], ["status", str(info.id)], ["group", "list"], ["group", "list", name]]:
		result = runner.invoke(app, args)
		assert result.exit_code == 0, result.exception
		assert name in Text.from_ansi(result.stdout).plain
