"""Value tests for the process termination and startup confirmation helpers"""

import signal
from typing import NoReturn

import psutil
import pytest

import sentinel_core.process as process
from sentinel_core.models import ProcessInfo


def info(*, create_time: float | None = 1.0) -> ProcessInfo:
	return ProcessInfo(
		id=1,
		pid=4242,
		name="api",
		cmd="python app.py",
		cwd="/",
		restart=False,
		started_at="",
		stdout_log="",
		stderr_log="",
		create_time=create_time,
	)


class FastClock:
	def __init__(self) -> None:
		self.now = 0.0

	def monotonic(self) -> float:
		return self.now

	def sleep(self, seconds: float) -> None:
		self.now += 1.0


class Member:
	def __init__(self, pid: int, status: str = psutil.STATUS_RUNNING) -> None:
		self.pid = pid
		self._status = status
		self.waited: list[float] = []

	def status(self) -> str:
		return self._status

	def wait(self, timeout: float = 0) -> int:
		self.waited.append(timeout)
		return 0


class ConfirmProc:
	def __init__(self, arguments: list[str]) -> None:
		self._arguments = arguments

	def cmdline(self) -> list[str]:
		return self._arguments


def use_members(monkeypatch: pytest.MonkeyPatch, members: list[Member], pgid: int | None = None) -> None:
	monkeypatch.setattr(process.psutil, "process_iter", lambda: list(members))
	group = {member.pid: pgid if pgid is not None else member.pid for member in members}
	monkeypatch.setattr(process.os, "getpgid", lambda pid: group[pid])


def use_signals(monkeypatch: pytest.MonkeyPatch, *, gone_on_first_call: bool = False) -> list[int]:
	group_signals: list[int] = []
	monkeypatch.setattr(process, "_signal_process_group", lambda pid, number: group_signals.append(number))
	calls = {"count": 0}

	def killpg(pid: int, number: int) -> None:
		calls["count"] += 1
		if gone_on_first_call and calls["count"] == 1:
			raise ProcessLookupError

	monkeypatch.setattr(process.os, "killpg", killpg)
	return group_signals


class TestTerminatePidIfAlive:
	def test_returns_when_the_group_is_gone(self, monkeypatch: pytest.MonkeyPatch) -> None:
		signals = use_signals(monkeypatch, gone_on_first_call=True)
		monkeypatch.setattr(process, "time", FastClock())

		process._terminate_pid_if_alive(4242)

		assert signals == [signal.SIGTERM]

	def test_returns_after_two_empty_scans(self, monkeypatch: pytest.MonkeyPatch) -> None:
		signals = use_signals(monkeypatch)
		clock = FastClock()
		monkeypatch.setattr(process, "time", clock)
		use_members(monkeypatch, [])

		process._terminate_pid_if_alive(4242)

		assert signals == [signal.SIGTERM]
		assert clock.now == 1.0

	def test_reaps_a_zombie_member(self, monkeypatch: pytest.MonkeyPatch) -> None:
		signals = use_signals(monkeypatch)
		monkeypatch.setattr(process, "time", FastClock())
		member = Member(4242, status=psutil.STATUS_ZOMBIE)
		use_members(monkeypatch, [member])

		process._terminate_pid_if_alive(4242)

		assert signals == [signal.SIGTERM]
		assert member.waited == [0, 0]

	def test_skips_a_member_of_another_group(self, monkeypatch: pytest.MonkeyPatch) -> None:
		signals = use_signals(monkeypatch)
		monkeypatch.setattr(process, "time", FastClock())
		use_members(monkeypatch, [Member(4243)], pgid=9999)

		process._terminate_pid_if_alive(4242)

		assert signals == [signal.SIGTERM]

	def test_force_raises_when_the_group_survives(self, monkeypatch: pytest.MonkeyPatch) -> None:
		signals = use_signals(monkeypatch)
		monkeypatch.setattr(process, "time", FastClock())
		use_members(monkeypatch, [Member(4242)])

		with pytest.raises(ValueError, match="Process group 4242 did not stop"):
			process._terminate_pid_if_alive(4242, force=True)

		assert signals == [signal.SIGKILL]

	def test_escalates_to_sigkill_after_the_deadline(self, monkeypatch: pytest.MonkeyPatch) -> None:
		signals = use_signals(monkeypatch)
		monkeypatch.setattr(process, "time", FastClock())
		use_members(monkeypatch, [Member(4242)])

		with pytest.raises(ValueError, match="Process group 4242 did not stop"):
			process._terminate_pid_if_alive(4242)

		assert signals == [signal.SIGTERM, signal.SIGKILL]


class TestConfirmStarted:
	def test_requires_a_create_time(self) -> None:
		with pytest.raises(ValueError, match="Process 'api' exited during startup"):
			process._confirm_started(info(create_time=None))

	def test_reports_a_missing_process(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(process, "managed_process", lambda target: None)

		with pytest.raises(ValueError, match="Process 'api' exited during startup"):
			process._confirm_started(info())

	def test_returns_when_argv_appears(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(process, "managed_process", lambda target: ConfirmProc(["python", "app.py"]))

		process._confirm_started(info())

	def test_reports_a_vanished_process(self, monkeypatch: pytest.MonkeyPatch) -> None:
		def cmdline() -> NoReturn:
			raise psutil.NoSuchProcess(4242)

		proc = ConfirmProc([])
		proc.cmdline = cmdline  # type: ignore[method-assign]
		monkeypatch.setattr(process, "managed_process", lambda target: proc)

		with pytest.raises(ValueError, match="Process 'api' exited during startup"):
			process._confirm_started(info())

	def test_times_out_while_argv_stays_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(process, "time", FastClock())
		monkeypatch.setattr(process, "managed_process", lambda target: ConfirmProc([]))

		with pytest.raises(ValueError, match=r"Process 'api' did not start within 0.1 seconds"):
			process._confirm_started(info(), timeout_seconds=0.1)
