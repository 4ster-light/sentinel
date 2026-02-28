"""Background restart monitor for processes with restart flag enabled"""

import logging
import os
import threading
import time
from typing import Callable

import psutil

from .process import start_process
from .state import ProcessInfo, State

logger = logging.getLogger(__name__)


def _is_process_running(pid: int) -> bool:
	try:
		proc = psutil.Process(pid)
		status = proc.status()
		return status != psutil.STATUS_ZOMBIE
	except (psutil.NoSuchProcess, psutil.AccessDenied):
		return False


class RestartMonitor:
	"""Monitors processes and automatically restarts those with restart=True when they exit."""

	def __init__(self, check_interval: float = 5.0) -> None:
		self._check_interval = check_interval
		self._thread: threading.Thread | None = None
		self._running = False
		self._lock = threading.Lock()
		self._restart_callback: Callable[[ProcessInfo], None] | None = None

	def set_restart_callback(self, callback: Callable[[ProcessInfo], None]) -> None:
		self._restart_callback = callback

	def start(self) -> None:
		with self._lock:
			if self._running:
				return

			self._running = True
			self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
			self._thread.start()

	def stop(self) -> None:
		with self._lock:
			if not self._running:
				return

			self._running = False

		if self._thread:
			self._thread.join(timeout=10)

	def _monitor_loop(self) -> None:
		while self._running:
			try:
				state = State()
				processes_to_restart: list[ProcessInfo] = []
				processes_to_cleanup: list[ProcessInfo] = []

				for info in list(state.processes.values()):
					if not psutil.pid_exists(info.pid) or not _is_process_running(info.pid):
						if info.restart:
							processes_to_restart.append(info)
						else:
							processes_to_cleanup.append(info)

				for info in processes_to_cleanup:
					try:
						state.remove_process(info.id)
					except Exception as e:
						logger.debug(f"Failed to clean up process {info.name} (id={info.id}): {e}")

				for info in processes_to_restart:
					try:
						old_id = info.id
						state.remove_process(old_id)
						os.chdir(info.cwd)
						new_info = start_process(
							state,
							info.cmd,
							name=info.name,
							restart=True,
							env=info.env,
							env_file=info.env_file,
						)
						if self._restart_callback:
							self._restart_callback(new_info)
						logger.debug(f"Restarted process {info.name} (old_pid={info.pid}, new_pid={new_info.pid})")
					except Exception as e:
						logger.error(f"Failed to restart process {info.name}: {e}")
						try:
							state.add_process(info)
						except Exception as add_error:
							logger.error(f"Failed to add dead process info for {info.name}: {add_error}")

				time.sleep(self._check_interval)
			except Exception as e:
				logger.error(f"Unexpected error in restart monitor loop: {e}", exc_info=True)
				time.sleep(self._check_interval)

	def is_running(self) -> bool:
		return self._running


class _MonitorSingleton:
	"""Thread-safe singleton registry for the restart monitor."""

	def __init__(self) -> None:
		self._monitor: RestartMonitor | None = None
		self._lock = threading.Lock()

	def get(self) -> RestartMonitor:
		"""Get or create the global restart monitor instance."""
		if self._monitor is None:
			with self._lock:
				if self._monitor is None:
					self._monitor = RestartMonitor()
		return self._monitor

	def reset(self) -> None:
		"""Reset the singleton (for testing)."""
		with self._lock:
			if self._monitor is not None:
				self._monitor.stop()
			self._monitor = None


_singleton = _MonitorSingleton()


def get_restart_monitor() -> RestartMonitor:
	"""Get or create the restart monitor instance."""
	return _singleton.get()


def start_restart_monitor(check_interval: float = 5.0) -> RestartMonitor:
	"""Start the restart monitor."""
	monitor = _singleton.get()
	if not monitor.is_running():
		monitor.start()
	return monitor


def stop_restart_monitor() -> None:
	"""Stop the restart monitor."""
	monitor = _singleton.get()
	if monitor.is_running():
		monitor.stop()
