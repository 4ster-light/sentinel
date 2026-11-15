"""Tests for dependency-aware process ordering"""

from pathlib import Path

import pytest

from sentinel_core.dependencies import DependencyError, start_order, stop_order
from sentinel_core.models import ProcessInfo
from sentinel_core.process import (
	batch_restart_processes,
	batch_start_processes,
	batch_stop_processes,
	start_process,
	stop_process,
)
from sentinel_core.state import State


def process(name: str, depends_on: tuple[str, ...] = ()) -> ProcessInfo:
	return ProcessInfo(
		id=0,
		pid=0,
		name=name,
		cmd="true",
		cwd="/",
		restart=False,
		started_at="",
		stdout_log="",
		stderr_log="",
		depends_on=list(depends_on),
	)


class TestStartOrder:
	def test_dependency_precedes_dependent(self):
		web = process("web", ("app",))
		app = process("app", ("cache", "db"))
		cache = process("cache")
		db = process("db")

		assert [p.name for p in start_order([web, app, cache, db])] == ["cache", "db", "app", "web"]

	def test_independent_processes_keep_input_order(self):
		assert [p.name for p in start_order([process("c"), process("a"), process("b")])] == ["c", "a", "b"]

	def test_diamond_dependencies(self):
		ordered = start_order(
			[
				process("app", ("left", "right")),
				process("left", ("base",)),
				process("right", ("base",)),
				process("base"),
			]
		)
		names = [p.name for p in ordered]

		assert names[0] == "base"
		assert names[-1] == "app"
		assert names.index("left") < names.index("app")
		assert names.index("right") < names.index("app")

	def test_duplicate_dependency_entries_do_not_break_ordering(self):
		ordered = start_order([process("app", ("db", "db")), process("db")])

		assert [p.name for p in ordered] == ["db", "app"]

	def test_missing_dependency_raises(self):
		with pytest.raises(DependencyError, match="neither in this batch nor running"):
			start_order([process("app", ("db",))])

	def test_running_dependency_is_accepted(self):
		ordered = start_order([process("app", ("db",))], available={"db"})

		assert [p.name for p in ordered] == ["app"]

	def test_cycle_reports_the_cycle(self):
		with pytest.raises(DependencyError, match=r"Dependency cycle: a -> b -> a"):
			start_order([process("a", ("b",)), process("b", ("a",))])

	def test_self_dependency_raises(self):
		with pytest.raises(DependencyError, match="cannot depend on itself"):
			start_order([process("loop", ("loop",))])

	def test_duplicate_names_raise(self):
		with pytest.raises(DependencyError, match="Duplicate process name 'a'"):
			start_order([process("a"), process("a")])


class TestStopOrder:
	def test_dependents_stop_first(self):
		assert [p.name for p in stop_order([process("db"), process("app", ("db",))])] == ["app", "db"]

	def test_unknown_dependencies_are_ignored(self):
		assert [p.name for p in stop_order([process("app", ("gone",))])] == ["app"]

	def test_cycle_falls_back_to_input_order(self):
		assert [p.name for p in stop_order([process("a", ("b",)), process("b", ("a",))])] == ["a", "b"]


class TestBatchOrdering:
	def test_start_process_rejects_self_dependency(self, state: State):
		with pytest.raises(ValueError, match="cannot depend on itself"):
			start_process(state, "sleep 30", name="loop", depends_on=["loop"])

	def test_batch_start_starts_dependencies_first(self, state: State, tmp_path: Path, wait_for, spawn_process):
		app_marker = tmp_path / "app.started"
		db_marker = tmp_path / "db.started"
		db_checked = tmp_path / "db.checked"
		db = spawn_process(
			f"sh -c 'test ! -f {app_marker} && touch {db_marker}; touch {db_checked}; sleep 30'",
			name="db",
		)
		app = start_process(
			state,
			f"sh -c 'touch {app_marker}; sleep 30'",
			name="app",
			depends_on=["db"],
		)
		stop_process(state, "db")
		stop_process(state, "app")
		for marker in (app_marker, db_marker, db_checked):
			marker.unlink(missing_ok=True)

		successful, failed = batch_start_processes(State(), [app, db])

		assert failed == []
		assert [info.name for info in successful] == ["db", "app"]
		wait_for(lambda: db_checked.exists() and app_marker.exists())
		assert db_marker.exists(), "app started before its dependency db"
		batch_stop_processes(State(), [db, app])

	def test_batch_start_rejects_a_stopped_dependency(self, state: State, spawn_process):
		spawn_process("sleep 30", name="db")
		app = start_process(state, "sleep 30", name="app", depends_on=["db"])
		stop_process(state, "db")
		stop_process(state, "app")

		with pytest.raises(DependencyError, match="depends on 'db'"):
			batch_start_processes(State(), [app])

	def test_batch_stop_stops_dependents_first(self, state: State, spawn_process):
		db = spawn_process("sleep 30", name="db")
		app = start_process(state, "sleep 30", name="app", depends_on=["db"])

		successful, failed = batch_stop_processes(State(), [db, app])

		assert failed == []
		assert [info.name for info in successful] == ["app", "db"]

	def test_batch_restart_follows_dependency_order(self, state: State, spawn_process):
		db = spawn_process("sleep 30", name="db")
		app = start_process(state, "sleep 30", name="app", depends_on=["db"])

		successful, failed = batch_restart_processes(State(), [app, db])

		assert failed == []
		assert [info.name for info in successful] == ["db", "app"]
