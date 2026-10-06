"""Background restart monitor for processes with restart flag enabled"""

import logging
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Generator

import psutil

from .health import run_health_check, should_run_health_check
from .logs import rotate_process_logs
from .process import restart_from_info
from .state import ProcessInfo, State

logger = logging.getLogger(__name__)


def _now_isoformat() -> str:
	return datetime.now().isoformat()


def _is_process_running(pid: int) -> bool:
	try:
		proc = psutil.Process(pid)
		status = proc.status()
		return status != psutil.STATUS_ZOMBIE
	except psutil.NoSuchProcess, psutil.AccessDenied:
		return False


@dataclass
class _ScanOutcome:
	to_restart: list[ProcessInfo] = field(default_factory=list)
	to_cleanup: list[ProcessInfo] = field(default_factory=list)
	health_updated: list[ProcessInfo] = field(default_factory=list)


def _scan(state: State) -> _ScanOutcome:
	"""Single pass over all processes: rotate logs, track health, decide restarts and cleanups."""
	outcome = _ScanOutcome()

	for info in list(state.processes.values()):
		rotate_process_logs(info.stdout_log, info.stderr_log)

		if not psutil.pid_exists(info.pid) or not _is_process_running(info.pid):
			if info.restart:
				outcome.to_restart.append(info)
			else:
				outcome.to_cleanup.append(info)
			continue

		if not should_run_health_check(info):
			continue

		is_healthy = run_health_check(info)
		info.health_last_checked_at = _now_isoformat()
		if is_healthy:
			info.health_failures = 0
		else:
			info.health_failures += 1
			if info.health_check and info.restart and info.health_failures >= info.health_check.failure_threshold:
				outcome.to_restart.append(info)
		outcome.health_updated.append(info)

	return outcome


def _apply_health_updates(state: State, updated: list[ProcessInfo]) -> None:
	for info in updated:
		state.add_process(info)


def _apply_cleanups(
	state: State,
	to_cleanup: list[ProcessInfo],
	on_cleanup: Callable[[ProcessInfo], None] | None = None,
) -> list[ProcessInfo]:
	cleaned_up: list[ProcessInfo] = []
	for info in to_cleanup:
		try:
			state.remove_process(info.id)
			cleaned_up.append(info)
			if on_cleanup:
				on_cleanup(info)
		except Exception as e:
			logger.debug(f"Failed to clean up process {info.name} (id={info.id}): {e}")
	return cleaned_up


def _apply_restarts(
	state: State,
	to_restart: list[ProcessInfo],
	on_restart: Callable[[ProcessInfo, ProcessInfo], None] | None = None,
) -> list[ProcessInfo]:
	restarted: list[ProcessInfo] = []
	for info in to_restart:
		try:
			state.remove_process(info.id)
			new_info = restart_from_info(state, info)
			restarted.append(new_info)
			if on_restart:
				on_restart(info, new_info)
			logger.debug(f"Restarted process {info.name} (old_pid={info.pid}, new_pid={new_info.pid})")
		except Exception as e:
			logger.error(f"Failed to restart process {info.name}: {e}")
			try:
				state.add_process(info)
			except Exception as add_error:
				logger.error(f"Failed to add dead process info for {info.name}: {add_error}")
	return restarted


class RestartMonitor:
	"""Monitors processes and automatically restarts those with restart=True when they exit."""

	def __init__(self, check_interval: float = 5.0) -> None:
		self._check_interval = check_interval
		self._thread: threading.Thread | None = None
		self._running = False
		self._stop_event = threading.Event()
		self._lock = threading.Lock()
		self._restart_callback: Callable[[ProcessInfo, ProcessInfo], None] | None = None

	def set_restart_callback(self, callback: Callable[[ProcessInfo, ProcessInfo], None]) -> None:
		self._restart_callback = callback

	def start(self) -> None:
		with self._lock:
			if self._running:
				return

			self._stop_event.clear()
			self._running = True
			self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
			self._thread.start()

	def stop(self) -> None:
		with self._lock:
			if not self._running:
				return

			self._running = False
			self._stop_event.set()

		if self._thread:
			self._thread.join(timeout=10)

	def _on_restart(self, old_info: ProcessInfo, new_info: ProcessInfo) -> None:
		if self._restart_callback:
			self._restart_callback(old_info, new_info)

	def _monitor_loop(self) -> None:
		while self._running:
			try:
				state = State()
				check_and_restart_processes(state, on_restart=self._on_restart)
			except Exception as e:
				logger.error(f"Unexpected error in restart monitor loop: {e}", exc_info=True)
			self._stop_event.wait(self._check_interval)

	def is_running(self) -> bool:
		return self._running


@contextmanager
def restart_monitor(check_interval: float = 5.0) -> Generator[RestartMonitor, None, None]:
	"""Context manager for restart monitor lifecycle.

	Ensures the monitor thread is properly started and stopped,
	even if an exception occurs during the monitored block.

	Usage:
	    with restart_monitor(check_interval=5.0) as monitor:
	        monitor.set_restart_callback(on_restart)
	        app.run(monitor=monitor)
	"""
	monitor = RestartMonitor(check_interval)
	monitor.start()
	try:
		yield monitor
	finally:
		monitor.stop()


def check_and_restart_processes(
	state: State,
	on_restart: Callable[[ProcessInfo, ProcessInfo], None] | None = None,
	on_cleanup: Callable[[ProcessInfo], None] | None = None,
) -> tuple[list[ProcessInfo], list[ProcessInfo]]:
	"""One-time check for dead processes and restart/cleanup as needed.

	This performs a single pass (no looping) to check all processes.
	Useful for "lazy" restart checking when CLI commands run.

	Args:
	    state: The State instance to use
	    on_restart: Optional callback(old_info, new_info) when a process is restarted
	    on_cleanup: Optional callback(info) when a non-restart process is cleaned up

	Returns:
	    Tuple of (restarted_processes, cleaned_up_processes)
	"""
	outcome = _scan(state)
	_apply_health_updates(state, outcome.health_updated)
	cleaned_up = _apply_cleanups(state, outcome.to_cleanup, on_cleanup)
	restarted = _apply_restarts(state, outcome.to_restart, on_restart)
	return restarted, cleaned_up
