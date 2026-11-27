"""Edge tests for the restart monitor: thread flags and log texts"""

import logging
from collections.abc import Generator
from contextlib import contextmanager
from typing import cast

import psutil
import pytest

import sentinel_core.restart_monitor as monitor
from sentinel_core.models import HealthCheckConfig, ProcessInfo
from sentinel_core.state import State


def info(
	ident: int = 1,
	name: str = "api",
	*,
	restart: bool = False,
	check: HealthCheckConfig | None = None,
	failures: int = 0,
) -> ProcessInfo:
	return ProcessInfo(
		id=ident,
		pid=4242,
		name=name,
		cmd="true",
		cwd="/",
		restart=restart,
		started_at="",
		stdout_log=f"/tmp/{name}.out",
		stderr_log=f"/tmp/{name}.err",
		create_time=1.0,
		health_check=check,
		health_failures=failures,
	)


class FakeStore:
	@contextmanager
	def locked(self) -> Generator[None]:
		yield

	def load(self) -> None:
		pass


class FakeState:
	def __init__(self, processes: list[ProcessInfo]) -> None:
		self.store = FakeStore()
		self.processes = {process.id: process for process in processes}
		self.added: list[ProcessInfo] = []
		self.removed: list[int] = []
		self.fail_add = False
		self.fail_remove = False

	def add_process(self, value: ProcessInfo) -> None:
		if self.fail_add:
			raise RuntimeError("add boom")
		self.added.append(value)

	def remove_process(self, ident: int) -> None:
		if self.fail_remove:
			raise RuntimeError("remove boom")
		self.removed.append(ident)

	def get_process(self, ident: int) -> ProcessInfo | None:
		return self.processes.get(ident)


def fake_state(processes: list[ProcessInfo]) -> tuple[State, FakeState]:
	fake = FakeState(processes)
	return cast(State, fake), fake


class TestMonitorEdges:
	def test_start_uses_a_daemon_thread(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(monitor, "check_and_restart_processes", lambda state, on_restart=None: None)
		running = monitor.RestartMonitor(check_interval=0.01)

		running.start()
		try:
			assert running._thread is not None
			assert running._thread.daemon is True
		finally:
			running.stop()

	def test_on_restart_passes_both_processes(self) -> None:
		running = monitor.RestartMonitor()
		seen: list[tuple[ProcessInfo, ProcessInfo]] = []
		running.set_restart_callback(lambda old, new: seen.append((old, new)))
		old = info()
		new = info(ident=2)

		running._on_restart(old, new)

		assert seen == [(old, new)]

	def test_scan_logs_the_identity_error_text(
		self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
	) -> None:
		monkeypatch.setattr(monitor, "rotate_process_logs", lambda out, err: None)

		def stale(process_info: ProcessInfo) -> object:
			raise monitor.ProcessIdentityError("stale")

		monkeypatch.setattr(monitor, "managed_process", stale)
		subject, _ = fake_state([info(restart=True)])
		caplog.set_level(logging.DEBUG)

		monitor._scan(subject)

		assert caplog.records[-1].getMessage() == "stale"

	def test_scan_logs_the_access_denied_text(
		self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
	) -> None:
		monkeypatch.setattr(monitor, "rotate_process_logs", lambda out, err: None)

		def denied(process_info: ProcessInfo) -> object:
			raise psutil.AccessDenied(4242)

		monkeypatch.setattr(monitor, "managed_process", denied)
		subject, _ = fake_state([info()])
		caplog.set_level(logging.DEBUG)

		monitor._scan(subject)

		assert caplog.records[-1].getMessage() == "Cannot inspect process api (pid=4242)"

	def test_scan_leaves_an_unhealthy_process_without_a_health_check(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(monitor, "rotate_process_logs", lambda out, err: None)
		monkeypatch.setattr(monitor, "managed_process", lambda target: object())
		monkeypatch.setattr(monitor, "should_run_health_check", lambda target: True)
		monkeypatch.setattr(monitor, "run_health_check", lambda target: False)
		target = info(restart=False, check=None, failures=5)
		subject, _ = fake_state([target])

		outcome = monitor._scan(subject)

		assert outcome.to_restart == []
		assert outcome.health_updated == [target]
		assert target.health_failures == 6

	def test_apply_restarts_logs_the_success(
		self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
	) -> None:
		replacement = info(ident=2)
		replacement.pid = 999
		monkeypatch.setattr(monitor, "restart_process", lambda state, ident: replacement)
		target = info()
		subject, fake = fake_state([target])
		caplog.set_level(logging.DEBUG)

		monitor._apply_restarts(subject, [target])

		assert fake.added == []
		assert any(
			record.getMessage() == "Restarted process api (old_pid=4242, new_pid=999)" for record in caplog.records
		)

	def test_apply_restarts_logs_the_restart_error(
		self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
	) -> None:
		def failing(state: State, ident: int) -> ProcessInfo:
			raise RuntimeError("boom")

		monkeypatch.setattr(monitor, "restart_process", failing)
		target = info()
		subject, fake = fake_state([target])
		caplog.set_level(logging.DEBUG)

		monitor._apply_restarts(subject, [target])

		assert any(record.getMessage() == "Failed to restart process api: boom" for record in caplog.records)
		assert fake.added == [target]
		assert target.stopped is False

	def test_apply_restarts_logs_the_add_error(
		self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
	) -> None:
		def failing(state: State, ident: int) -> ProcessInfo:
			raise RuntimeError("boom")

		monkeypatch.setattr(monitor, "restart_process", failing)
		target = info()
		subject, fake = fake_state([target])
		fake.fail_add = True
		caplog.set_level(logging.DEBUG)

		monitor._apply_restarts(subject, [target])

		assert any(
			record.getMessage() == "Failed to add dead process info for api: add boom" for record in caplog.records
		)

	def test_apply_cleanups_logs_the_cleanup_error(self, caplog: pytest.LogCaptureFixture) -> None:
		target = info()
		subject, fake = fake_state([target])
		fake.fail_remove = True
		caplog.set_level(logging.DEBUG)

		monitor._apply_cleanups(subject, [target])

		assert caplog.records[-1].getMessage() == "Failed to clean up process api (id=1): remove boom"
