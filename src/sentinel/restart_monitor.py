"""Background restart monitor for processes with restart flag enabled"""

import logging
import os
import threading
import time
from contextlib import contextmanager
from typing import Callable, Generator

import psutil

from .process import start_process
from .state import ProcessInfo, State

logger = logging.getLogger(__name__)


def _is_process_running(pid: int) -> bool:
	try:
		proc = psutil.Process(pid)
		status = proc.status()
		return status != psutil.STATUS_ZOMBIE
	except psutil.NoSuchProcess, psutil.AccessDenied:
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
	restarted: list[ProcessInfo] = []
	cleaned_up: list[ProcessInfo] = []

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
			cleaned_up.append(info)
			if on_cleanup:
				on_cleanup(info)
		except Exception as e:
			logger.debug(f"Failed to clean up process {info.name} (id={info.id}): {e}")

	for info in processes_to_restart:
		try:
			old_id = info.id
			old_cwd = os.getcwd()
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
			os.chdir(old_cwd)
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

	return restarted, cleaned_up
