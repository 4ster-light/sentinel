"""Value tests for the cluster and lazy restart helpers"""

from collections.abc import Callable
from io import StringIO
from types import SimpleNamespace
from typing import cast

import pytest
from rich.console import Console

import sentinel_cli.cluster as cluster
import sentinel_cli.main as main
from sentinel_core.models import ProcessInfo
from sentinel_core.state import State


def info(name: str = "api", ident: int = 1) -> ProcessInfo:
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


class TestClusterRunning:
	def test_running_when_managed(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(cluster, "managed_process", lambda target: object())

		assert cluster._running(info()) is True

	def test_not_running_when_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(cluster, "managed_process", lambda target: None)

		assert cluster._running(info()) is False

	def test_not_running_on_an_identity_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
		def stale(target: ProcessInfo) -> object:
			raise cluster.ProcessIdentityError("stale")

		monkeypatch.setattr(cluster, "managed_process", stale)

		assert cluster._running(info()) is False


class TestLazyRestartCheck:
	def test_skips_when_the_daemon_runs(self, monkeypatch: pytest.MonkeyPatch) -> None:
		calls: list[int] = []
		monkeypatch.setattr(main, "is_daemon_running", lambda: True)
		monkeypatch.setattr(main, "check_and_restart_processes", lambda *args, **kwargs: calls.append(1))

		main._perform_lazy_restart_check(cast(State, SimpleNamespace()))

		assert calls == []

	def test_runs_the_check_with_both_callbacks(self, monkeypatch: pytest.MonkeyPatch) -> None:
		seen: dict[str, object] = {}

		def fake(state: State, *, on_restart: object = None, on_cleanup: object = None) -> tuple[list, list]:
			seen["restart"] = on_restart
			seen["cleanup"] = on_cleanup
			return [], []

		monkeypatch.setattr(main, "is_daemon_running", lambda: False)
		monkeypatch.setattr(main, "check_and_restart_processes", fake)

		main._perform_lazy_restart_check(cast(State, SimpleNamespace()))

		assert callable(seen["restart"])
		assert callable(seen["cleanup"])

	def test_prints_the_restart_and_cleanup_messages(self, monkeypatch: pytest.MonkeyPatch) -> None:
		out = StringIO()
		monkeypatch.setattr(main, "console", Console(file=out, width=80, height=24))
		seen: dict[str, object] = {}

		def fake(state: State, *, on_restart: object = None, on_cleanup: object = None) -> tuple[list, list]:
			seen["restart"] = on_restart
			seen["cleanup"] = on_cleanup
			return [], []

		monkeypatch.setattr(main, "is_daemon_running", lambda: False)
		monkeypatch.setattr(main, "check_and_restart_processes", fake)

		main._perform_lazy_restart_check(cast(State, SimpleNamespace()))
		restart = cast(Callable[[ProcessInfo, ProcessInfo], None], seen["restart"])
		cleanup = cast(Callable[[ProcessInfo], None], seen["cleanup"])
		restart(info("api", 1), info("api", 2))
		cleanup(info("api", 1))

		text = out.getvalue()
		assert "Auto-restarted" in text
		assert "old_pid: 4242, new_pid: 4242" in text
		assert "Cleaned up dead process" in text

	def test_prints_a_blank_line_after_changes(self, monkeypatch: pytest.MonkeyPatch) -> None:
		out = StringIO()
		monkeypatch.setattr(main, "console", Console(file=out, width=80, height=24))
		monkeypatch.setattr(main, "is_daemon_running", lambda: False)
		monkeypatch.setattr(main, "check_and_restart_processes", lambda *args, **kwargs: ([object()], []))

		main._perform_lazy_restart_check(cast(State, SimpleNamespace()))

		assert out.getvalue() == "\n"

	def test_prints_nothing_without_changes(self, monkeypatch: pytest.MonkeyPatch) -> None:
		out = StringIO()
		monkeypatch.setattr(main, "console", Console(file=out, width=80, height=24))
		monkeypatch.setattr(main, "is_daemon_running", lambda: False)
		monkeypatch.setattr(main, "check_and_restart_processes", lambda *args, **kwargs: ([], []))

		main._perform_lazy_restart_check(cast(State, SimpleNamespace()))

		assert out.getvalue() == ""
