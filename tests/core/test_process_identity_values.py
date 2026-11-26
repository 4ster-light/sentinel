"""Value tests for the managed process identity checks"""

from datetime import datetime
from typing import NoReturn

import psutil
import pytest

import sentinel_core.process as process
from sentinel_core.models import ProcessInfo


def info(*, create_time: float | None = None, started_at: str = "", cmd: str = "python app.py") -> ProcessInfo:
	return ProcessInfo(
		id=1,
		pid=4242,
		name="api",
		cmd=cmd,
		cwd="/",
		restart=False,
		started_at=started_at,
		stdout_log="",
		stderr_log="",
		create_time=create_time,
	)


def legacy_started() -> tuple[str, float]:
	started_at = "2026-01-01T00:00:00"
	return started_at, datetime.fromisoformat(started_at).timestamp()


class FakeProc:
	def __init__(
		self,
		*,
		create_time: float = 1000.0,
		status: str = psutil.STATUS_RUNNING,
		cwd: str | Exception = "/",
	) -> None:
		self._create_time = create_time
		self._status = status
		self._cwd = cwd

	def create_time(self) -> float:
		return self._create_time

	def status(self) -> str:
		return self._status

	def cwd(self) -> str:
		if isinstance(self._cwd, Exception):
			raise self._cwd
		return self._cwd

	def wait(self, timeout: float = 0) -> int:
		return 0


def use_proc(monkeypatch: pytest.MonkeyPatch, proc: object) -> None:
	monkeypatch.setattr(process.psutil, "Process", lambda pid: proc)


def use_group(monkeypatch: pytest.MonkeyPatch, pgid: int | Exception) -> None:
	def getpgid(pid: int) -> int:
		if isinstance(pgid, Exception):
			raise pgid
		return pgid

	monkeypatch.setattr(process.os, "getpgid", getpgid)


def use_cmdline(monkeypatch: pytest.MonkeyPatch, arguments: list[str]) -> None:
	monkeypatch.setattr(process, "_cmdline_after_exec", lambda proc: arguments)


class TestManagedProcess:
	def test_stopped_process_has_no_handle(self) -> None:
		target = info()
		target.stopped = True

		assert process.managed_process(target) is None

	def test_a_non_positive_pid_has_no_handle(self) -> None:
		target = info()
		target.pid = 0

		assert process.managed_process(target) is None

	def test_matching_create_time_returns_the_handle(self, monkeypatch: pytest.MonkeyPatch) -> None:
		proc = FakeProc(create_time=1000.0)
		use_proc(monkeypatch, proc)
		target = info(create_time=1000.0)

		assert process.managed_process(target) is proc

	def test_a_reused_pid_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
		use_proc(monkeypatch, FakeProc(create_time=2000.0))
		target = info(create_time=1000.0)

		assert process.managed_process(target) is None

	def test_a_gone_process_has_no_handle(self, monkeypatch: pytest.MonkeyPatch) -> None:
		def gone(pid: int) -> NoReturn:
			raise psutil.NoSuchProcess(pid)

		monkeypatch.setattr(process.psutil, "Process", gone)

		assert process.managed_process(info(create_time=1000.0)) is None

	def test_a_zombie_has_no_handle(self, monkeypatch: pytest.MonkeyPatch) -> None:
		proc = FakeProc(create_time=1000.0, status=psutil.STATUS_ZOMBIE)
		use_proc(monkeypatch, proc)

		assert process.managed_process(info(create_time=1000.0)) is None
		assert process.managed_process(info(create_time=1000.0), include_zombie=True) is proc

	def test_accepts_a_matching_legacy_process(self, monkeypatch: pytest.MonkeyPatch) -> None:
		started_at, created = legacy_started()
		proc = FakeProc(create_time=created)
		use_proc(monkeypatch, proc)
		use_group(monkeypatch, 4242)
		use_cmdline(monkeypatch, ["python", "app.py"])
		target = info(started_at=started_at)

		assert process.managed_process(target) is proc
		assert target.create_time == created

	def test_accepts_a_shell_wrapped_legacy_process(self, monkeypatch: pytest.MonkeyPatch) -> None:
		started_at, created = legacy_started()
		use_proc(monkeypatch, FakeProc(create_time=created))
		use_group(monkeypatch, 4242)
		use_cmdline(monkeypatch, ["sh", "-c", "python app.py"])

		assert process.managed_process(info(started_at=started_at)) is not None

	def test_accepts_an_unsettled_legacy_argv(self, monkeypatch: pytest.MonkeyPatch) -> None:
		started_at, created = legacy_started()
		use_proc(monkeypatch, FakeProc(create_time=created))
		use_group(monkeypatch, 4242)
		use_cmdline(monkeypatch, [])

		assert process.managed_process(info(started_at=started_at)) is not None

	def test_reports_an_unreadable_legacy_record(self, monkeypatch: pytest.MonkeyPatch) -> None:
		use_proc(monkeypatch, FakeProc(create_time=1000.0))

		with pytest.raises(process.ProcessIdentityError) as excinfo:
			process.managed_process(info(started_at="not a date"))

		assert str(excinfo.value) == "Cannot verify legacy process 'api': unreadable start time or command"

	def test_reports_a_cmdline_mismatch(self, monkeypatch: pytest.MonkeyPatch) -> None:
		started_at, created = legacy_started()
		use_proc(monkeypatch, FakeProc(create_time=created))
		use_group(monkeypatch, 4242)
		use_cmdline(monkeypatch, ["other"])

		with pytest.raises(process.ProcessIdentityError) as excinfo:
			process.managed_process(info(started_at=started_at))

		assert str(excinfo.value) == (
			"Cannot verify legacy process 'api'; its state was left unchanged "
			"(command line ['other'] does not match 'python app.py')"
		)

	def test_reports_a_late_creation(self, monkeypatch: pytest.MonkeyPatch) -> None:
		started_at, created = legacy_started()
		use_proc(monkeypatch, FakeProc(create_time=created + 1.0))
		use_group(monkeypatch, 4242)
		use_cmdline(monkeypatch, ["python", "app.py"])

		with pytest.raises(process.ProcessIdentityError, match=r"creation time .* is after the recorded start"):
			process.managed_process(info(started_at=started_at))

	def test_reports_an_unreadable_cwd(self, monkeypatch: pytest.MonkeyPatch) -> None:
		started_at, created = legacy_started()
		use_proc(monkeypatch, FakeProc(create_time=created, cwd=psutil.AccessDenied(4242)))
		use_group(monkeypatch, 4242)
		use_cmdline(monkeypatch, ["python", "app.py"])

		with pytest.raises(process.ProcessIdentityError) as excinfo:
			process.managed_process(info(started_at=started_at))

		assert str(excinfo.value) == (
			"Cannot verify legacy process 'api'; its state was left unchanged "
			"(cannot read the process working directory)"
		)

	def test_reports_a_cwd_mismatch(self, monkeypatch: pytest.MonkeyPatch) -> None:
		started_at, created = legacy_started()
		use_proc(monkeypatch, FakeProc(create_time=created, cwd="/other"))
		use_group(monkeypatch, 4242)
		use_cmdline(monkeypatch, ["python", "app.py"])

		with pytest.raises(process.ProcessIdentityError) as excinfo:
			process.managed_process(info(started_at=started_at))

		assert str(excinfo.value) == (
			"Cannot verify legacy process 'api'; its state was left unchanged "
			"(working directory '/other' does not match '/')"
		)

	def test_reports_an_unreadable_process_group(self, monkeypatch: pytest.MonkeyPatch) -> None:
		started_at, created = legacy_started()
		use_proc(monkeypatch, FakeProc(create_time=created))
		use_group(monkeypatch, OSError("denied"))
		use_cmdline(monkeypatch, ["python", "app.py"])

		with pytest.raises(process.ProcessIdentityError) as excinfo:
			process.managed_process(info(started_at=started_at))

		assert str(excinfo.value) == (
			"Cannot verify legacy process 'api'; its state was left unchanged (cannot read the process group)"
		)

	def test_reports_a_process_group_mismatch(self, monkeypatch: pytest.MonkeyPatch) -> None:
		started_at, created = legacy_started()
		use_proc(monkeypatch, FakeProc(create_time=created))
		use_group(monkeypatch, 4243)
		use_cmdline(monkeypatch, ["python", "app.py"])

		with pytest.raises(process.ProcessIdentityError) as excinfo:
			process.managed_process(info(started_at=started_at))

		assert str(excinfo.value) == (
			"Cannot verify legacy process 'api'; its state was left unchanged "
			"(process group 4243 is not the leader 4242)"
		)

	def test_reports_all_problems_in_order(self, monkeypatch: pytest.MonkeyPatch) -> None:
		started_at, created = legacy_started()
		use_proc(monkeypatch, FakeProc(create_time=created, cwd="/other"))
		use_group(monkeypatch, 4243)
		use_cmdline(monkeypatch, ["other"])

		with pytest.raises(process.ProcessIdentityError) as excinfo:
			process.managed_process(info(started_at=started_at))

		assert str(excinfo.value) == (
			"Cannot verify legacy process 'api'; its state was left unchanged "
			"(command line ['other'] does not match 'python app.py'; "
			"working directory '/other' does not match '/'; process group 4243 is not the leader 4242)"
		)
