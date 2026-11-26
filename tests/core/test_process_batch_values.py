"""Value tests for the batch restart and stop helpers"""

from types import SimpleNamespace
from typing import cast

import pytest

import sentinel_core.process as process
from sentinel_core.models import ProcessInfo
from sentinel_core.state import State


def info(name: str, ident: int, depends_on: tuple[str, ...] = ()) -> ProcessInfo:
	return ProcessInfo(
		id=ident,
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


def fake_state() -> State:
	return cast(State, SimpleNamespace())


class TestBatchStop:
	def test_stops_in_reverse_dependency_order(self, monkeypatch: pytest.MonkeyPatch) -> None:
		calls: list[tuple[int, bool]] = []
		monkeypatch.setattr(
			process,
			"stop_process",
			lambda state, ident, force=False: calls.append((ident, force)) or info("stopped", ident),
		)
		db = info("db", 1)
		web = info("web", 2, ("db",))

		successful, failed = process.batch_stop_processes(fake_state(), [db, web], force=True)

		assert calls == [(2, True), (1, True)]
		assert [p.name for p in successful] == ["stopped", "stopped"]
		assert failed == []

	def test_records_a_failure_and_continues(self, monkeypatch: pytest.MonkeyPatch) -> None:
		def failing(state: State, ident: int, force: bool = False) -> ProcessInfo:
			if ident == 2:
				raise ValueError("boom")
			return info("db", 1)

		monkeypatch.setattr(process, "stop_process", failing)
		db = info("db", 1)
		web = info("web", 2, ("db",))

		successful, failed = process.batch_stop_processes(fake_state(), [db, web])

		assert [p.name for p in successful] == ["db"]
		assert [(p.name, message) for p, message in failed] == [("web", "boom")]


class TestBatchRestart:
	def test_restarts_in_start_order_and_confirms_dependencies(self, monkeypatch: pytest.MonkeyPatch) -> None:
		restarted: list[int] = []
		confirmed: list[str] = []
		records = {1: info("db", 1), 2: info("web", 2)}
		monkeypatch.setattr(process, "running_dependency_problems", lambda state, deps: [])
		monkeypatch.setattr(
			process,
			"restart_process",
			lambda state, ident: restarted.append(ident) or records[ident],
		)
		monkeypatch.setattr(process, "_confirm_started", lambda target: confirmed.append(target.name))
		db = info("db", 1)
		web = info("web", 2, ("db",))

		successful, failed = process.batch_restart_processes(fake_state(), [web, db])

		assert restarted == [1, 2]
		assert confirmed == ["db"]
		assert [p.name for p in successful] == ["db", "web"]
		assert failed == []

	def test_records_a_dependency_problem(self, monkeypatch: pytest.MonkeyPatch) -> None:
		restarted: list[int] = []

		def problems(state: State, deps: list[str]) -> list[str]:
			return ["db is not running"] if deps else []

		monkeypatch.setattr(process, "running_dependency_problems", problems)
		monkeypatch.setattr(process, "_confirm_started", lambda target: None)
		monkeypatch.setattr(
			process,
			"restart_process",
			lambda state, ident: restarted.append(ident) or info("db", ident),
		)
		db = info("db", 1)
		web = info("web", 2, ("db",))

		successful, failed = process.batch_restart_processes(fake_state(), [db, web])

		assert restarted == [1]
		assert [p.name for p in successful] == ["db"]
		assert [(p.name, message) for p, message in failed] == [("web", "db is not running")]

	def test_records_a_restart_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
		def failing(state: State, ident: int) -> ProcessInfo:
			raise ValueError("boom")

		monkeypatch.setattr(process, "running_dependency_problems", lambda state, deps: [])
		monkeypatch.setattr(process, "restart_process", failing)

		successful, failed = process.batch_restart_processes(fake_state(), [info("db", 1)])

		assert successful == []
		assert [(p.name, message) for p, message in failed] == [("db", "boom")]
