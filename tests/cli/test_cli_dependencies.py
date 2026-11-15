"""Tests for dependency handling in the CLI"""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from sentinel_cli import app
from sentinel_core.process import batch_stop_processes, start_process, stop_process
from sentinel_core.state import State

runner = CliRunner()


@pytest.fixture(autouse=True)
def stop_started_processes(state: State):
	yield
	batch_stop_processes(state, state.list_processes(), force=True)


def run_process(name: str, command: str = "sleep 30", depends_on: list[str] | None = None) -> None:
	args = ["run", command, "--name", name]
	for dependency in depends_on or []:
		args.extend(["--depends-on", dependency])
	result = runner.invoke(app, args)
	assert result.exit_code == 0, result.output


class TestRunDependencies:
	def test_depends_on_is_recorded(self, state: State):
		run_process("db")
		run_process("app", depends_on=["db"])

		info = State().find_process_by_name("app")

		assert info is not None
		assert info.depends_on == ["db"]

	def test_depends_on_multiple_dependencies(self, state: State):
		run_process("db")
		run_process("cache")
		run_process("app", depends_on=["db", "cache"])

		info = State().find_process_by_name("app")
		assert info is not None
		assert info.depends_on == ["db", "cache"]

	def test_unknown_dependency_is_rejected(self, state: State):
		result = runner.invoke(app, ["run", "sleep 30", "--name", "app", "--depends-on", "db"])

		assert result.exit_code == 1
		assert "Unknown dependency 'db'" in result.stderr
		assert State().find_process_by_name("app") is None

	def test_stopped_dependency_is_rejected(self, state: State):
		run_process("db")
		stop_process(State(), "db")

		result = runner.invoke(app, ["run", "sleep 30", "--name", "app", "--depends-on", "db"])

		assert result.exit_code == 1
		assert "Dependency 'db' is not running" in result.stderr
		assert State().find_process_by_name("app") is None

	def test_self_dependency_is_rejected(self, state: State):
		result = runner.invoke(app, ["run", "sleep 30", "--name", "loop", "--depends-on", "loop"])

		assert result.exit_code == 1
		assert "cannot name the process itself" in result.stderr

	def test_depends_on_cannot_combine_with_instances(self, state: State):
		result = runner.invoke(
			app,
			["run", "sleep 30", "--name", "app", "--instances", "2", "--depends-on", "db"],
		)

		assert result.exit_code == 1
		assert "--depends-on cannot be combined with --instances" in result.stderr

	def test_status_shows_dependencies(self, state: State):
		run_process("db")
		run_process("app", depends_on=["db"])

		result = runner.invoke(app, ["status", "app"])

		assert result.exit_code == 0
		assert "Depends:" in result.stdout
		assert "db" in result.stdout


class TestGroupDependencyOrder:
	def test_group_start_starts_dependencies_first(self, state: State, tmp_path: Path, wait_for):
		app_marker = tmp_path / "app.started"
		db_marker = tmp_path / "db.started"
		db_checked = tmp_path / "db.checked"
		state.create_group("stack")
		db = start_process(
			state,
			f"sh -c 'test ! -f {app_marker} && touch {db_marker}; touch {db_checked}; sleep 30'",
			name="db",
			group="stack",
		)
		app_info = start_process(
			state,
			f"sh -c 'touch {app_marker}; sleep 30'",
			name="app",
			group="stack",
			depends_on=["db"],
		)
		result = runner.invoke(app, ["group", "stop", "stack"])
		assert result.exit_code == 0, result.output
		for marker in (app_marker, db_marker, db_checked):
			marker.unlink(missing_ok=True)

		result = runner.invoke(app, ["group", "start", "stack"])

		assert result.exit_code == 0, result.output
		wait_for(lambda: db_checked.exists() and app_marker.exists())
		assert db_marker.exists(), "app started before its dependency db"
		assert app_info.depends_on == ["db"]
		stop_process(State(), db.id)
		stop_process(State(), app_info.id)

	def test_group_start_reports_a_cycle(self, state: State):
		state.create_group("cycle")
		first = start_process(state, "sleep 30", name="first", group="cycle")
		second = start_process(state, "sleep 30", name="second", group="cycle")
		stop_process(state, first.id)
		stop_process(state, second.id)
		first.stopped = True
		second.stopped = True
		first.depends_on = ["second"]
		second.depends_on = ["first"]
		state.add_process(first)
		state.add_process(second)

		result = runner.invoke(app, ["group", "start", "cycle"])

		assert result.exit_code == 1
		assert "Dependency cycle" in result.stdout
