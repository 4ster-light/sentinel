"""Value tests for the process priority and status helpers"""

from types import SimpleNamespace
from typing import NoReturn

import psutil
import pytest

import sentinel_core.process as process
from sentinel_core.models import ProcessInfo, ProcessStatus


def info() -> ProcessInfo:
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
	)


class FakeProc:
	def __init__(self) -> None:
		self.nice_calls: list[int] = []
		self.ionice_calls: list[tuple[object, ...]] = []
		self.nice_error: Exception | None = None
		self.ionice_error: Exception | None = None

	def nice(self, value: int) -> None:
		self.nice_calls.append(value)
		if self.nice_error is not None:
			raise self.nice_error

	def ionice(self, *args: object) -> None:
		self.ionice_calls.append(args)
		if self.ionice_error is not None:
			raise self.ionice_error


def use_proc(monkeypatch: pytest.MonkeyPatch, proc: object) -> None:
	monkeypatch.setattr(process.psutil, "Process", lambda pid: proc)


class TestProcessPriority:
	def test_sets_nice_without_ionice(self, monkeypatch: pytest.MonkeyPatch) -> None:
		proc = FakeProc()
		use_proc(monkeypatch, proc)

		assert process._apply_process_priority(1, 5, None, None) == []
		assert proc.nice_calls == [5]
		assert proc.ionice_calls == []

	def test_reports_a_nice_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
		proc = FakeProc()
		proc.nice_error = PermissionError("denied")
		use_proc(monkeypatch, proc)

		assert process._apply_process_priority(1, 5, None, None) == [
			"Could not set CPU priority (nice=5): denied. Using default CPU priority."
		]

	def test_idle_class(self, monkeypatch: pytest.MonkeyPatch) -> None:
		proc = FakeProc()
		use_proc(monkeypatch, proc)

		assert process._apply_process_priority(1, None, "idle", None) == []
		assert proc.ionice_calls == [(psutil.IOPRIO_CLASS_IDLE,)]

	def test_best_effort_default_priority(self, monkeypatch: pytest.MonkeyPatch) -> None:
		proc = FakeProc()
		use_proc(monkeypatch, proc)

		assert process._apply_process_priority(1, None, "best_effort", None) == []
		assert proc.ionice_calls == [(psutil.IOPRIO_CLASS_BE, 4)]

	def test_best_effort_given_priority(self, monkeypatch: pytest.MonkeyPatch) -> None:
		proc = FakeProc()
		use_proc(monkeypatch, proc)

		assert process._apply_process_priority(1, None, "best_effort", 6) == []
		assert proc.ionice_calls == [(psutil.IOPRIO_CLASS_BE, 6)]

	def test_best_effort_rejects_an_out_of_range_priority(self, monkeypatch: pytest.MonkeyPatch) -> None:
		use_proc(monkeypatch, FakeProc())

		with pytest.raises(ValueError, match="best-effort priority must be between 0 and 7"):
			process._apply_process_priority(1, None, "best_effort", 8)

	def test_realtime_default_priority(self, monkeypatch: pytest.MonkeyPatch) -> None:
		proc = FakeProc()
		use_proc(monkeypatch, proc)

		assert process._apply_process_priority(1, None, "realtime", None) == []
		assert proc.ionice_calls == [(psutil.IOPRIO_CLASS_RT, 0)]

	def test_realtime_given_priority(self, monkeypatch: pytest.MonkeyPatch) -> None:
		proc = FakeProc()
		use_proc(monkeypatch, proc)

		assert process._apply_process_priority(1, None, "realtime", 3) == []
		assert proc.ionice_calls == [(psutil.IOPRIO_CLASS_RT, 3)]

	def test_realtime_rejects_an_out_of_range_priority(self, monkeypatch: pytest.MonkeyPatch) -> None:
		use_proc(monkeypatch, FakeProc())

		with pytest.raises(ValueError, match="realtime priority must be between 0 and 7"):
			process._apply_process_priority(1, None, "realtime", 9)

	def test_rejects_an_unknown_class(self, monkeypatch: pytest.MonkeyPatch) -> None:
		use_proc(monkeypatch, FakeProc())

		with pytest.raises(ValueError, match="unknown ionice class: weird"):
			process._apply_process_priority(1, None, "weird", None)

	def test_reports_a_platform_without_ionice(self, monkeypatch: pytest.MonkeyPatch) -> None:
		proc = FakeProc()
		use_proc(monkeypatch, proc)
		monkeypatch.delattr(psutil, "IOPRIO_CLASS_IDLE")

		assert process._apply_process_priority(1, None, "idle", None) == [
			"I/O scheduling class (ionice) is not available on this platform; ionice was skipped."
		]
		assert proc.ionice_calls == []

	def test_reports_a_process_without_ionice(self, monkeypatch: pytest.MonkeyPatch) -> None:
		class NoIonice:
			def nice(self, value: int) -> None:
				pass

		monkeypatch.setattr(process.psutil, "Process", lambda pid: NoIonice())

		assert process._apply_process_priority(1, None, "best_effort", None) == [
			"I/O scheduling class (ionice) is not available on this platform; ionice was skipped."
		]

	def test_reports_an_ionice_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
		proc = FakeProc()
		proc.ionice_error = PermissionError("denied")
		use_proc(monkeypatch, proc)

		assert process._apply_process_priority(1, None, "best_effort", None) == [
			"Could not apply ionice (best_effort): denied. Using default I/O scheduling."
		]


class StatusProc:
	def __init__(
		self,
		*,
		status: str = "sleeping",
		children: list[StatusProc] | None = None,
		cpu: tuple[float, ...] = (1.0, 2.0),
		rss: tuple[int, ...] = (1024,),
	) -> None:
		self._status = status
		self._children = children or []
		self._cpu = list(cpu)
		self._rss = list(rss)

	def status(self) -> str:
		return self._status

	def children(self, recursive: bool = False) -> list[StatusProc]:
		return list(self._children)

	def cpu_percent(self) -> float:
		return self._cpu.pop(0)

	def memory_info(self) -> SimpleNamespace:
		return SimpleNamespace(rss=self._rss.pop(0))


class TestProcessStatus:
	def test_stopped_process(self, monkeypatch: pytest.MonkeyPatch) -> None:
		target = info()
		target.stopped = True
		monkeypatch.setattr(process, "managed_process", lambda target: None)

		assert process.get_process_status(target) == ProcessStatus(
			running=False, status="stopped", cpu_percent=0, memory_mb=0
		)

	def test_exited_process(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(process, "managed_process", lambda target: None)

		assert process.get_process_status(info()) == ProcessStatus(
			running=False, status="exited", cpu_percent=0, memory_mb=0
		)

	def test_running_process_sums_the_tree(self, monkeypatch: pytest.MonkeyPatch) -> None:
		child = StatusProc(cpu=(2.0, 3.0), rss=(2048,))
		main = StatusProc(children=[child], cpu=(1.0, 2.0), rss=(1024,))
		monkeypatch.setattr(process, "managed_process", lambda target: main)
		monkeypatch.setattr(process.time, "sleep", lambda seconds: None)

		status = process.get_process_status(info())

		assert status == ProcessStatus(
			running=True,
			status="sleeping",
			cpu_percent=5.0,
			memory_mb=(1024 + 2048) / (1024 * 1024),
		)

	def test_a_gone_process_reports_exited(self, monkeypatch: pytest.MonkeyPatch) -> None:
		def gone(target: ProcessInfo) -> NoReturn:
			raise psutil.NoSuchProcess(1)

		monkeypatch.setattr(process, "managed_process", gone)

		assert process.get_process_status(info()) == ProcessStatus(
			running=False, status="exited", cpu_percent=0, memory_mb=0
		)

	def test_denied_access_reports_unknown(self, monkeypatch: pytest.MonkeyPatch) -> None:
		def denied(target: ProcessInfo) -> NoReturn:
			raise psutil.AccessDenied(1)

		monkeypatch.setattr(process, "managed_process", denied)

		assert process.get_process_status(info()) == ProcessStatus(
			running=False, status="unknown", cpu_percent=0, memory_mb=0
		)

	def test_an_identity_error_reports_unknown(self, monkeypatch: pytest.MonkeyPatch) -> None:
		def stale(target: ProcessInfo) -> NoReturn:
			raise process.ProcessIdentityError("stale")

		monkeypatch.setattr(process, "managed_process", stale)

		assert process.get_process_status(info()) == ProcessStatus(
			running=False, status="unknown", cpu_percent=0, memory_mb=0
		)

	def test_a_child_that_disappears_is_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
		child = StatusProc(cpu=(1.0,), rss=())

		def gone() -> float:
			raise psutil.NoSuchProcess(2)

		child.cpu_percent = gone  # type: ignore[method-assign]
		main = StatusProc(children=[child], cpu=(1.0, 2.0), rss=(1024,))
		monkeypatch.setattr(process, "managed_process", lambda target: main)
		monkeypatch.setattr(process.time, "sleep", lambda seconds: None)

		status = process.get_process_status(info())

		assert status.cpu_percent == 2.0
		assert status.memory_mb == 1024 / (1024 * 1024)
