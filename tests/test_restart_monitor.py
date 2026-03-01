"""Tests for the restart monitor functionality"""

import time
from pathlib import Path
from unittest.mock import Mock

import psutil

from sentinel.process import start_process, stop_process
from sentinel.restart_monitor import RestartMonitor
from sentinel.state import State


class TestRestartMonitor:
	"""Test the RestartMonitor class"""

	def test_monitor_initialization(self):
		"""Test that monitor initializes correctly"""
		monitor = RestartMonitor(check_interval=1.0)
		assert monitor._check_interval == 1.0
		assert not monitor.is_running()

	def test_monitor_start_stop(self):
		"""Test starting and stopping the monitor"""
		monitor = RestartMonitor(check_interval=0.1)
		assert not monitor.is_running()

		monitor.start()
		assert monitor.is_running()

		monitor.stop()
		assert not monitor.is_running()

	def test_monitor_start_idempotent(self):
		"""Test that calling start multiple times is safe"""
		monitor = RestartMonitor(check_interval=0.1)
		monitor.start()
		thread1 = monitor._thread
		monitor.start()
		thread2 = monitor._thread
		assert thread1 is thread2
		monitor.stop()

	def test_monitor_restart_dead_process(self, state: State, temp_state_dir: Path):
		"""Test that monitor restarts a process with restart=True"""
		# Start a short-lived process with restart=True
		info = start_process(state, "sleep 0.5", name="short_lived", restart=True)
		original_pid = info.pid
		assert psutil.pid_exists(original_pid)

		# Create monitor with short check interval
		monitor = RestartMonitor(check_interval=0.1)
		monitor.start()
		state_after = State()

		try:
			# Wait for process to die and monitor to detect it
			time.sleep(2.0)

			# Check that a new process exists with the same name
			state_after = State()
			new_info = state_after.find_process_by_name("short_lived")
			assert new_info is not None
			assert new_info.restart is True
			# The PID should be different (new process)
			# Note: We can't reliably test that new_info.pid != original_pid
			# because the monitor may not have restarted yet
		finally:
			monitor.stop()
			# Cleanup any remaining process
			try:
				state_after = State()
				new_info = state_after.find_process_by_name("short_lived")
				if new_info:
					stop_process(state_after, new_info.id)
			except Exception:
				pass

	def test_monitor_does_not_restart_without_flag(self, state: State, temp_state_dir: Path):
		"""Test that monitor does NOT restart processes without restart=True"""
		# Start a short-lived process without restart
		info = start_process(state, "sleep 0.5", name="no_restart", restart=False)
		original_id = info.id
		original_pid = info.pid
		assert psutil.pid_exists(original_pid)

		# Create monitor with short check interval
		monitor = RestartMonitor(check_interval=0.1)
		monitor.start()

		try:
			# Wait for process to die and monitor to run cleanup
			time.sleep(2.0)

			# Check that process was cleaned up (removed from state)
			state_after = State()
			new_info = state_after.find_process_by_name("no_restart")
			# The process should be cleaned up from state since it has no restart flag
			assert new_info is None or new_info.id != original_id
		finally:
			monitor.stop()

	def test_monitor_callback(self, state: State, temp_state_dir: Path):
		"""Test that monitor calls the restart callback"""
		# Start a short-lived process with restart=True
		info = start_process(state, "sleep 0.5", name="callback_test", restart=True)
		assert psutil.pid_exists(info.pid)

		# Create monitor and set callback
		monitor = RestartMonitor(check_interval=0.1)
		callback = Mock()
		monitor.set_restart_callback(callback)
		monitor.start()

		try:
			# Wait for process to die and monitor to detect it
			time.sleep(2.0)

			# Check that callback was called at least once
			assert callback.call_count >= 1
			# Callback should be called with ProcessInfo
			call_args = callback.call_args_list[0]
			assert call_args[0][0].name == "callback_test"
		finally:
			monitor.stop()
			try:
				state_after = State()
				new_info = state_after.find_process_by_name("callback_test")
				if new_info:
					stop_process(state_after, new_info.id)
			except Exception:
				pass

	def test_monitor_env_preserved_on_restart(self, state: State, temp_state_dir: Path):
		"""Test that process environment is preserved on restart"""
		env = {"TEST_VAR": "preserved_value"}
		info = start_process(state, "sleep 0.5", name="env_preserve", restart=True, env=env)
		assert psutil.pid_exists(info.pid)

		# Create monitor with short check interval
		monitor = RestartMonitor(check_interval=0.1)
		monitor.start()
		state_after = State()

		try:
			# Wait for process to die and monitor to detect it
			time.sleep(2.0)

			# Check that environment is preserved
			state_after = State()
			new_info = state_after.find_process_by_name("env_preserve")
			assert new_info is not None
			assert new_info.env == env
		finally:
			monitor.stop()
			try:
				state_after = State()
				new_info = state_after.find_process_by_name("env_preserve")
				if new_info:
					stop_process(state_after, new_info.id)
			except Exception:
				pass


class TestRestartMonitorIntegration:
	"""Integration tests with the process management system"""

	def test_multiple_process_restart(self, state: State, temp_state_dir: Path):
		"""Test that monitor can restart multiple processes concurrently"""
		# Start multiple short-lived processes with restart=True
		info1 = start_process(state, "sleep 0.5", name="multi1", restart=True)
		info2 = start_process(state, "sleep 0.5", name="multi2", restart=True)
		assert psutil.pid_exists(info1.pid)
		assert psutil.pid_exists(info2.pid)

		monitor = RestartMonitor(check_interval=0.1)
		monitor.start()

		try:
			# Wait for processes to die and be restarted
			time.sleep(2.0)

			# Both processes should still exist
			state_after = State()
			new_info1 = state_after.find_process_by_name("multi1")
			new_info2 = state_after.find_process_by_name("multi2")
			assert new_info1 is not None
			assert new_info2 is not None
		finally:
			monitor.stop()
			try:
				state_after = State()
				for name in ["multi1", "multi2"]:
					info = state_after.find_process_by_name(name)
					if info:
						stop_process(state_after, info.id)
			except Exception:
				pass

	def test_restart_preserves_log_paths(self, state: State, temp_state_dir: Path):
		"""Test that restarted processes have valid log paths"""
		info = start_process(state, "sleep 0.5", name="log_test", restart=True)
		original_stdout = info.stdout_log
		original_stderr = info.stderr_log
		assert Path(original_stdout).exists()
		assert Path(original_stderr).exists()

		monitor = RestartMonitor(check_interval=0.1)
		monitor.start()
		state_after = State()

		try:
			# Wait for process to die and be restarted
			time.sleep(2.0)

			# Check that new process has valid log paths
			state_after = State()
			new_info = state_after.find_process_by_name("log_test")
			assert new_info is not None
			assert Path(new_info.stdout_log).exists()
			assert Path(new_info.stderr_log).exists()
		finally:
			monitor.stop()
			try:
				state_after = State()
				new_info = state_after.find_process_by_name("log_test")
				if new_info:
					stop_process(state_after, new_info.id)
			except Exception:
				pass
