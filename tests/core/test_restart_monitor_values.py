"""Value tests for the restart monitor scan and apply helpers"""

from collections.abc import Generator
from contextlib import contextmanager
from threading import Event
from typing import cast

import psutil
import pytest

import sentinel_core.restart_monitor as monitor
from sentinel_core.models import HealthCheckConfig, ProcessInfo
from sentinel_core.state import State


def health() -> HealthCheckConfig:
	return HealthCheckConfig(
		kind="tcp", target="localhost:9000", interval_seconds=10.0, timeout_seconds=2.0, failure_threshold=3
	)


def info(
	name: str = "api",
	ident: int = 1,
	*,
	stopped: bool = False,
	restart: bool = False,
	create_time: float | None = 1.0,
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
		stopped=stopped,
		create_time=create_time,
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
		self.processes = {p.id: p for p in processes}
		self.added: list[ProcessInfo] = []
		self.removed: list[int] = []
		self.current = {p.id: p for p in processes}

	def add_process(self, info: ProcessInfo) -> None:
		self.added.append(info)

	def remove_process(self, ident: int) -> None:
		self.removed.append(ident)

	def get_process(self, ident: int) -> ProcessInfo | None:
		return self.current.get(ident)


def state(processes: list[ProcessInfo]) -> tuple[State, FakeState]:
	fake = FakeState(processes)
	return cast(State, fake), fake


class TestScan:
	def test_skips_a_stopped_process(self, monkeypatch: pytest.MonkeyPatch) -> None:
		rotated: list[tuple[str, str]] = []
		monkeypatch.setattr(monitor, "rotate_process_logs", lambda out, err: rotated.append((out, err)))
		subject, _ = state([info(stopped=True)])

		outcome = monitor._scan(subject)

		assert rotated == []
		assert outcome.to_restart == []
		assert outcome.to_cleanup == []
		assert outcome.health_updated == []

	def test_rotates_each_running_process(self, monkeypatch: pytest.MonkeyPatch) -> None:
		rotated: list[tuple[str, str]] = []
		monkeypatch.setattr(monitor, "rotate_process_logs", lambda out, err: rotated.append((out, err)))
		monkeypatch.setattr(monitor, "managed_process", lambda target: object())
		subject, _ = state([info()])

		monitor._scan(subject)

		assert rotated == [("/tmp/api.out", "/tmp/api.err")]

	def test_records_a_legacy_create_time(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(monitor, "rotate_process_logs", lambda out, err: None)
		target = info(create_time=None)

		def managed(process_info: ProcessInfo) -> object:
			process_info.create_time = 2.0
			return object()

		monkeypatch.setattr(monitor, "managed_process", managed)
		subject, _ = state([target])

		outcome = monitor._scan(subject)

		assert outcome.health_updated == [target]

	def test_reports_an_identity_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(monitor, "rotate_process_logs", lambda out, err: None)

		def stale(process_info: ProcessInfo) -> object:
			raise monitor.ProcessIdentityError("stale")

		monkeypatch.setattr(monitor, "managed_process", stale)
		subject, _ = state([info(restart=True)])

		outcome = monitor._scan(subject)

		assert outcome.to_restart == []
		assert outcome.to_cleanup == []

	def test_reports_access_denied(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(monitor, "rotate_process_logs", lambda out, err: None)

		def denied(process_info: ProcessInfo) -> object:
			raise psutil.AccessDenied(4242)

		monkeypatch.setattr(monitor, "managed_process", denied)
		subject, _ = state([info(restart=True)])

		outcome = monitor._scan(subject)

		assert outcome.to_restart == []

	def test_restarts_a_dead_process_with_the_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(monitor, "rotate_process_logs", lambda out, err: None)
		monkeypatch.setattr(monitor, "managed_process", lambda target: None)
		target = info(restart=True)
		subject, _ = state([target])

		assert monitor._scan(subject).to_restart == [target]

	def test_cleans_up_a_dead_process_without_the_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(monitor, "rotate_process_logs", lambda out, err: None)
		monkeypatch.setattr(monitor, "managed_process", lambda target: None)
		target = info(restart=False)
		subject, _ = state([target])

		assert monitor._scan(subject).to_cleanup == [target]

	def test_skips_health_when_it_is_not_due(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(monitor, "rotate_process_logs", lambda out, err: None)
		monkeypatch.setattr(monitor, "managed_process", lambda target: object())
		monkeypatch.setattr(monitor.should_run_health_check, "__call__", lambda target: False, raising=False)
		monkeypatch.setattr(monitor, "should_run_health_check", lambda target: False)
		target = info(check=health())
		subject, _ = state([target])

		outcome = monitor._scan(subject)

		assert outcome.health_updated == []

	def test_resets_failures_when_healthy(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(monitor, "rotate_process_logs", lambda out, err: None)
		monkeypatch.setattr(monitor, "managed_process", lambda target: object())
		monkeypatch.setattr(monitor, "should_run_health_check", lambda target: True)
		monkeypatch.setattr(monitor, "run_health_check", lambda target: True)
		monkeypatch.setattr(monitor, "_now_isoformat", lambda: "now")
		target = info(check=health(), failures=2)
		subject, _ = state([target])

		outcome = monitor._scan(subject)

		assert target.health_failures == 0
		assert target.health_last_checked_at == "now"
		assert outcome.health_updated == [target]

	def test_increments_failures_when_unhealthy(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(monitor, "rotate_process_logs", lambda out, err: None)
		monkeypatch.setattr(monitor, "managed_process", lambda target: object())
		monkeypatch.setattr(monitor, "should_run_health_check", lambda target: True)
		monkeypatch.setattr(monitor, "run_health_check", lambda target: False)
		monkeypatch.setattr(monitor, "_now_isoformat", lambda: "now")
		target = info(check=health(), failures=0)
		subject, _ = state([target])

		outcome = monitor._scan(subject)

		assert target.health_failures == 1
		assert outcome.health_updated == [target]
		assert outcome.to_restart == []

	def test_restarts_at_the_failure_threshold(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(monitor, "rotate_process_logs", lambda out, err: None)
		monkeypatch.setattr(monitor, "managed_process", lambda target: object())
		monkeypatch.setattr(monitor, "should_run_health_check", lambda target: True)
		monkeypatch.setattr(monitor, "run_health_check", lambda target: False)
		monkeypatch.setattr(monitor, "_now_isoformat", lambda: "now")
		target = info(check=health(), failures=2, restart=True)
		subject, _ = state([target])

		outcome = monitor._scan(subject)

		assert target.health_failures == 3
		assert outcome.to_restart == [target]


class TestApply:
	def test_restarts_and_calls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
		old = info()
		new = info(ident=2)
		monkeypatch.setattr(monitor, "restart_process", lambda state, ident: new)
		subject, _ = state([old])
		calls: list[tuple[ProcessInfo, ProcessInfo]] = []

		restarted = monitor._apply_restarts(subject, [old], on_restart=lambda a, b: calls.append((a, b)))

		assert restarted == [new]
		assert calls == [(old, new)]

	def test_restores_the_dead_info_after_a_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
		def failing(state: State, ident: int) -> ProcessInfo:
			raise ValueError("boom")

		monkeypatch.setattr(monitor, "restart_process", failing)
		current = info()
		current.stopped = True
		subject, fake = state([current])

		restarted = monitor._apply_restarts(subject, [current])

		assert restarted == []
		assert current.stopped is False
		assert fake.added == [current]

	def test_cleans_up_and_calls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
		target = info()
		subject, fake = state([target])
		calls: list[ProcessInfo] = []

		cleaned = monitor._apply_cleanups(subject, [target], on_cleanup=calls.append)

		assert cleaned == [target]
		assert fake.removed == [1]
		assert calls == [target]

	def test_records_a_cleanup_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
		target = info()
		subject, fake = state([target])

		def failing(ident: int) -> None:
			raise ValueError("boom")

		monkeypatch.setattr(fake, "remove_process", failing)

		assert monitor._apply_cleanups(subject, [target]) == []

	def test_applies_health_updates(self) -> None:
		first = info()
		second = info(ident=2)
		subject, fake = state([first, second])

		monitor._apply_health_updates(subject, [first, second])

		assert fake.added == [first, second]


class FakeThread:
	def __init__(self, target: object, daemon: bool) -> None:
		self.target = target
		self.daemon = daemon
		self.started = False
		self.joined: list[float | None] = []

	def start(self) -> None:
		self.started = True

	def join(self, timeout: float | None = None) -> None:
		self.joined.append(timeout)


class TestMonitorLifecycle:
	def test_start_is_idempotent(self, monkeypatch: pytest.MonkeyPatch) -> None:
		threads: list[FakeThread] = []
		monkeypatch.setattr(
			monitor.threading,
			"Thread",
			lambda target, daemon: threads.append(FakeThread(target, daemon)) or threads[-1],
		)
		subject = monitor.RestartMonitor(0.1)

		subject.start()
		subject.start()

		assert subject.is_running() is True
		assert len(threads) == 1
		assert threads[0].started is True

	def test_stop_joins_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
		threads: list[FakeThread] = []
		monkeypatch.setattr(
			monitor.threading,
			"Thread",
			lambda target, daemon: threads.append(FakeThread(target, daemon)) or threads[-1],
		)
		subject = monitor.RestartMonitor(0.1)
		subject.start()

		subject.stop()
		subject.stop()

		assert subject.is_running() is False
		assert threads[0].joined == [10]

	def test_callbacks_are_optional_and_forwarded(self) -> None:
		subject = monitor.RestartMonitor(0.1)
		restarts: list[tuple[ProcessInfo, ProcessInfo]] = []
		scales: list[tuple[str, int, int]] = []
		subject._on_restart(info(), info(ident=2))
		subject._on_scale("web", 1, 2)
		subject.set_restart_callback(lambda a, b: restarts.append((a, b)))
		subject.set_scale_callback(lambda name, before, after: scales.append((name, before, after)))
		subject._on_restart(info(), info(ident=2))
		subject._on_scale("web", 1, 2)

		assert len(restarts) == 1
		assert scales == [("web", 1, 2)]

	def test_context_manager_starts_and_stops(self, monkeypatch: pytest.MonkeyPatch) -> None:
		calls: list[str] = []
		monkeypatch.setattr(monitor.RestartMonitor, "start", lambda self: calls.append("start"))
		monkeypatch.setattr(monitor.RestartMonitor, "stop", lambda self: calls.append("stop"))

		with monitor.restart_monitor(0.1) as subject:
			assert isinstance(subject, monitor.RestartMonitor)

		assert calls == ["start", "stop"]

	def test_check_and_restart_orders_the_steps(self, monkeypatch: pytest.MonkeyPatch) -> None:
		outcome = monitor._ScanOutcome(to_restart=[info()], to_cleanup=[info(ident=2)], health_updated=[info(ident=3)])
		calls: list[str] = []
		monkeypatch.setattr(monitor, "_scan", lambda state: outcome)
		monkeypatch.setattr(monitor, "_apply_health_updates", lambda state, updated: calls.append("health"))
		monkeypatch.setattr(
			monitor, "_apply_cleanups", lambda state, cleanup, callback: calls.append("cleanup") or ["cleaned"]
		)
		monkeypatch.setattr(
			monitor, "_apply_restarts", lambda state, restart, callback: calls.append("restart") or ["restarted"]
		)
		subject, _ = state([])

		restarted, cleaned = monitor.check_and_restart_processes(subject)

		assert calls == ["health", "cleanup", "restart"]
		assert restarted == ["restarted"]
		assert cleaned == ["cleaned"]

	def test_monitor_loop_runs_one_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
		subject = monitor.RestartMonitor(0.1)
		subject._running = True
		calls: list[str] = []

		class StopEvent:
			def wait(self, seconds: float) -> bool:
				subject._running = False
				return True

		subject._stop_event = cast(Event, StopEvent())
		monkeypatch.setattr(monitor, "check_and_restart_processes", lambda state, on_restart: calls.append("check"))
		monkeypatch.setattr(monitor, "apply_autoscaling", lambda state, last, on_scale: calls.append("scale"))

		subject._monitor_loop()

		assert calls == ["check", "scale"]

	def test_initial_state(self) -> None:
		subject = monitor.RestartMonitor(0.25)

		assert subject._check_interval == 0.25
		assert subject._thread is None
		assert subject._running is False
		assert subject._stop_event.is_set() is False
		assert subject._restart_callback is None
		assert subject._scale_callback is None
		assert subject._autoscale_adjustments == {}

	def test_default_interval(self) -> None:
		assert monitor.RestartMonitor()._check_interval == 5.0

	def test_loop_waits_for_the_interval(self, monkeypatch: pytest.MonkeyPatch) -> None:
		subject = monitor.RestartMonitor(0.25)
		subject._running = True
		waits: list[float] = []

		class StopEvent:
			def wait(self, seconds: float) -> bool:
				waits.append(seconds)
				subject._running = False
				return True

		subject._stop_event = cast(Event, StopEvent())
		monkeypatch.setattr(monitor, "check_and_restart_processes", lambda state, on_restart: None)
		monkeypatch.setattr(monitor, "apply_autoscaling", lambda state, last, on_scale: None)

		subject._monitor_loop()

		assert waits == [0.25]
