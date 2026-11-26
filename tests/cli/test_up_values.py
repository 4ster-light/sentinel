"""Value tests for the up command and its running check"""

from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
import typer
from rich.console import Console

import sentinel_cli.up as up
from sentinel_core.config import UpReport
from sentinel_core.models import ProcessInfo
from sentinel_core.state import State


def info(name: str, ident: int = 1) -> ProcessInfo:
	return ProcessInfo(
		id=ident,
		pid=4242,
		name=name,
		cmd="true",
		cwd="/",
		restart=True,
		started_at="",
		stdout_log="",
		stderr_log="",
	)


def report(**kwargs: object) -> UpReport:
	values: dict[str, object] = {
		"started": [],
		"failed": [],
		"skipped_running": [],
		"conflicts": [],
		"groups_created": [],
		"expected": [],
	}
	values.update(kwargs)
	return UpReport(**values)


class FakeState:
	def __init__(self, processes: list[ProcessInfo]) -> None:
		self.by_name = {process.name: process for process in processes}

	def find_process_by_name(self, name: str) -> ProcessInfo | None:
		return self.by_name.get(name)


def consoles(monkeypatch: pytest.MonkeyPatch) -> tuple[StringIO, StringIO]:
	out = StringIO()
	err = StringIO()
	monkeypatch.setattr(up, "console", Console(file=out, width=80, height=24))
	monkeypatch.setattr(up, "error_console", Console(file=err, width=80, height=24))
	return out, err


class TestNotRunning:
	def test_collects_every_dead_case(self, monkeypatch: pytest.MonkeyPatch) -> None:
		def managed(target: ProcessInfo) -> object:
			if target.name == "dead":
				return None
			if target.name == "stale":
				raise up.ProcessIdentityError("stale")
			return object()

		monkeypatch.setattr(up, "managed_process", managed)
		alive = info("alive")
		stopped = info("stopped")
		stopped.stopped = True
		state = cast(State, FakeState([alive, stopped, info("dead"), info("stale")]))

		assert up._not_running(state, ["alive", "stopped", "dead", "stale", "missing"]) == [
			"stopped",
			"dead",
			"stale",
			"missing",
		]


class TestUp:
	def test_requires_a_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
		_out, err = consoles(monkeypatch)
		monkeypatch.setattr(up, "discover_config", lambda: None)

		with pytest.raises(typer.Exit) as excinfo:
			up.up(config=None)

		assert excinfo.value.exit_code == 1
		assert "No configuration file found" in err.getvalue()

	def test_reports_a_config_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
		_out, err = consoles(monkeypatch)

		def failing(path: Path) -> dict[str, object]:
			raise ValueError("bad config")

		monkeypatch.setattr(up, "load_config", failing)

		with pytest.raises(typer.Exit) as excinfo:
			up.up(config=Path("/tmp/sentinel.toml"))

		assert excinfo.value.exit_code == 1
		assert "bad config" in err.getvalue()

	def test_prints_every_report_line(self, monkeypatch: pytest.MonkeyPatch) -> None:
		_out, err = consoles(monkeypatch)
		started = info("api", 7)
		monkeypatch.setattr(up, "load_config", lambda path: {})
		monkeypatch.setattr(up, "load_state", lambda: cast(State, SimpleNamespace()))
		monkeypatch.setattr(
			up,
			"run_up",
			lambda state, path, specs: report(
				groups_created=["web"],
				started=[started],
				skipped_running=["db"],
				conflicts=[("api", "other")],
				failed=[("job", "boom")],
				expected=["api"],
			),
		)
		monkeypatch.setattr(up, "_not_running", lambda state, expected: [])

		with pytest.raises(typer.Exit) as excinfo:
			up.up(config=Path("/tmp/sentinel.toml"))

		assert excinfo.value.exit_code == 1

		text = _out.getvalue() + err.getvalue()
		assert "Created group web" in text
		assert "Started api (id: 7, pid: 4242)" in text
		assert "db already running" in text
		assert "different command: other" in text
		assert "Failed to start job: boom" in text

	def test_reports_a_process_that_is_not_running(self, monkeypatch: pytest.MonkeyPatch) -> None:
		_out, err = consoles(monkeypatch)
		monkeypatch.setattr(up, "load_config", lambda path: {})
		monkeypatch.setattr(up, "load_state", lambda: cast(State, SimpleNamespace()))
		monkeypatch.setattr(up, "run_up", lambda state, path, specs: report(expected=["api"]))
		monkeypatch.setattr(up, "_not_running", lambda state, expected: ["api"])

		with pytest.raises(typer.Exit) as excinfo:
			up.up(config=Path("/tmp/sentinel.toml"))

		assert excinfo.value.exit_code == 1
		assert "api is not running" in err.getvalue()
