"""Bounded tests for the post-fork command line probe"""

from typing import cast

import psutil
import pytest

import sentinel_core.process as process


class FakeClock:
	def __init__(self) -> None:
		self.now = 0.0

	def monotonic(self) -> float:
		return self.now

	def sleep(self, seconds: float) -> None:
		self.now += seconds
		assert self.now < 5.0, "the poll loop did not stop at the deadline"


class FakeProcess:
	def __init__(self, arguments: list[list[str]]) -> None:
		self.arguments = arguments
		self.calls = 0

	def cmdline(self) -> list[str]:
		index = min(self.calls, len(self.arguments) - 1)
		self.calls += 1
		return self.arguments[index]


class TestCmdlineAfterExec:
	def test_returns_the_arguments_after_the_first_poll(self, monkeypatch: pytest.MonkeyPatch) -> None:
		clock = FakeClock()
		monkeypatch.setattr(process, "time", clock)
		proc = FakeProcess([[], ["python", "run.py"]])

		assert process._cmdline_after_exec(cast(psutil.Process, proc)) == ["python", "run.py"]
		assert proc.calls == 2
		assert clock.now == pytest.approx(0.01)

	def test_returns_empty_arguments_at_the_deadline(self, monkeypatch: pytest.MonkeyPatch) -> None:
		clock = FakeClock()
		monkeypatch.setattr(process, "time", clock)
		proc = FakeProcess([[]])

		assert process._cmdline_after_exec(cast(psutil.Process, proc)) == []
		assert 0.1 <= clock.now < 0.2

	def test_does_not_poll_when_the_arguments_are_ready(self, monkeypatch: pytest.MonkeyPatch) -> None:
		clock = FakeClock()
		monkeypatch.setattr(process, "time", clock)
		proc = FakeProcess([["python", "run.py"]])

		assert process._cmdline_after_exec(cast(psutil.Process, proc)) == ["python", "run.py"]
		assert proc.calls == 1
		assert clock.now == 0.0
