import os
import time
from pathlib import Path
from unittest.mock import patch

import psutil
import pytest

from sentinel.process import (
	check_restart_needed,
	cleanup_dead_processes,
	get_process_status,
	restart_process,
	start_process,
	stop_process,
)
from sentinel.state import ProcessInfo


class TestStartProcess:
	def test_start_simple_process(self, state, temp_state_dir: Path):
		info = start_process(state, "sleep 10", name="sleeper")

		assert info.name == "sleeper"
		assert info.cmd == "sleep 10"
		assert info.cwd == os.getcwd()
		assert info.restart is False
		assert psutil.pid_exists(info.pid)
		assert info.id in state.processes

		# Cleanup
		proc = psutil.Process(info.pid)
		proc.terminate()
		proc.wait()

	def test_start_process_auto_name(self, state, temp_state_dir: Path):
		info = start_process(state, "sleep 5")

		assert info.name == "sleep"
		assert psutil.pid_exists(info.pid)

		# Cleanup
		proc = psutil.Process(info.pid)
		proc.terminate()
		proc.wait()

	def test_start_process_with_restart(self, state, temp_state_dir: Path):
		info = start_process(state, "sleep 10", name="restarter", restart=True)

		assert info.restart is True
		assert psutil.pid_exists(info.pid)

		# Cleanup
		proc = psutil.Process(info.pid)
		proc.terminate()
		proc.wait()

	def test_start_process_with_env(self, state, temp_state_dir: Path):
		env = {"TEST_VAR": "test_value"}
		info = start_process(state, "sleep 5", name="env_test", env=env)

		assert info.env == env
		assert psutil.pid_exists(info.pid)

		# Cleanup
		proc = psutil.Process(info.pid)
		proc.terminate()
		proc.wait()

	def test_start_process_duplicate_name(self, state, temp_state_dir: Path):
		start_process(state, "sleep 10", name="duplicate")

		with pytest.raises(ValueError, match="already exists"):
			start_process(state, "sleep 10", name="duplicate")

		# Cleanup
		for info in state.list_processes():
			try:
				proc = psutil.Process(info.pid)
				proc.terminate()
				proc.wait()
			except psutil.NoSuchProcess:
				pass

	def test_start_process_creates_logs(self, state, temp_state_dir: Path):
		info = start_process(state, "echo 'hello world'", name="logger")

		# Give it a moment to write
		time.sleep(0.5)

		stdout_path = Path(info.stdout_log)
		stderr_path = Path(info.stderr_log)

		assert stdout_path.exists()
		assert stderr_path.exists()

		# Check content
		time.sleep(0.5)
		content = stdout_path.read_text()
		assert "hello world" in content


class TestStopProcess:
	def test_stop_process_by_id(self, state, temp_state_dir: Path):
		info = start_process(state, "sleep 60", name="stoppable")
		assert psutil.pid_exists(info.pid)

		stopped = stop_process(state, info.id)

		assert stopped.id == info.id
		assert info.id not in state.processes

		# Wait for process to die
		time.sleep(0.5)
		assert not psutil.pid_exists(info.pid)

	def test_stop_process_by_name(self, state, temp_state_dir: Path):
		info = start_process(state, "sleep 60", name="stoppable")
		assert psutil.pid_exists(info.pid)

		stopped = stop_process(state, "stoppable")

		assert stopped.name == "stoppable"
		assert info.id not in state.processes

		time.sleep(0.5)
		assert not psutil.pid_exists(info.pid)

	def test_stop_process_force(self, state, temp_state_dir: Path):
		# Start a process that ignores SIGTERM
		info = start_process(state, "sleep 60", name="stubborn")
		assert psutil.pid_exists(info.pid)

		stopped = stop_process(state, info.id, force=True)

		assert stopped.id == info.id

		# Wait for force kill to complete
		time.sleep(1.0)

		# Process should be dead or removed from state
		assert stopped.id not in state.processes

	def test_stop_nonexistent_process(self, state):
		with pytest.raises(ValueError, match="not found"):
			stop_process(state, 999)

		with pytest.raises(ValueError, match="not found"):
			stop_process(state, "nonexistent")

	def test_stop_already_dead_process(self, state, temp_state_dir: Path):
		info = start_process(state, "echo 'done'", name="quick")

		# Wait for it to finish
		time.sleep(0.5)

		# Should not raise an error
		stopped = stop_process(state, info.id)
		assert stopped.id == info.id
		assert info.id not in state.processes


class TestRestartProcess:
	def test_restart_process(self, state, temp_state_dir: Path):
		original = start_process(state, "sleep 60", name="restartable", restart=True)
		original_pid = original.pid

		assert psutil.pid_exists(original_pid)

		restarted = restart_process(state, original.id)

		assert restarted.name == "restartable"
		assert restarted.cmd == "sleep 60"
		assert restarted.restart is True
		assert restarted.pid != original_pid
		assert psutil.pid_exists(restarted.pid)

		# Original should be gone
		time.sleep(0.5)
		assert not psutil.pid_exists(original_pid)

		# Cleanup
		proc = psutil.Process(restarted.pid)
		proc.terminate()
		proc.wait()

	def test_restart_process_by_name(self, state, temp_state_dir: Path):
		original = start_process(state, "sleep 60", name="restartable")
		original_pid = original.pid

		restarted = restart_process(state, "restartable")

		assert restarted.pid != original_pid
		assert psutil.pid_exists(restarted.pid)

		# Cleanup
		proc = psutil.Process(restarted.pid)
		proc.terminate()
		proc.wait()

	def test_restart_nonexistent_process(self, state):
		with pytest.raises(ValueError, match="not found"):
			restart_process(state, 999)


class TestGetProcessStatus:
	def test_get_status_running_process(self, state, temp_state_dir: Path):
		info = start_process(state, "sleep 60", name="running")

		status = get_process_status(info)

		assert status["running"] is True
		assert status["cpu_percent"] >= 0
		assert status["memory_mb"] > 0

		# Cleanup
		proc = psutil.Process(info.pid)
		proc.terminate()
		proc.wait()

	def test_get_status_dead_process(self, state, temp_state_dir: Path):
		info = ProcessInfo(
			id=1,
			pid=99999,
			name="dead",
			cmd="sleep 60",
			cwd="/tmp",
			restart=False,
			started_at="2024-01-01T00:00:00",
			stdout_log="/tmp/dead.stdout.log",
			stderr_log="/tmp/dead.stderr.log",
		)

		status = get_process_status(info)

		assert status["running"] is False
		assert status["status"] == "exited"
		assert status["cpu_percent"] == 0
		assert status["memory_mb"] == 0


class TestCleanupDeadProcesses:
	def test_cleanup_dead_processes(self, state, temp_state_dir: Path):
		# Create a live process for reference
		live_info = start_process(state, "sleep 60", name="alive")

		# Manually create a dead process entry (simulates a process that exited)
		# Use a PID that definitely doesn't exist (larger than max allowed)
		dead_info = ProcessInfo(
			id=state.get_next_id(),
			pid=2147483647,  # Max 32-bit int, extremely unlikely to be real
			name="dead",
			cmd="sleep 60",
			cwd="/tmp",
			restart=False,
			started_at="2024-01-01T00:00:00",
			stdout_log="/tmp/dead.stdout.log",
			stderr_log="/tmp/dead.stderr.log",
		)
		state.add_process(dead_info)

		# Verify we have 2 processes before cleanup
		assert len(state.list_processes()) == 2

		dead = cleanup_dead_processes(state)

		# The fake PID should be detected as dead
		assert len(dead) == 1
		assert dead[0].name == "dead"
		assert dead[0].id not in state.processes
		assert live_info.id in state.processes

		# Cleanup
		proc = psutil.Process(live_info.pid)
		proc.terminate()
		proc.wait()

	def test_cleanup_no_dead_processes(self, state, temp_state_dir: Path):
		info = start_process(state, "sleep 60", name="alive")

		dead = cleanup_dead_processes(state)

		assert len(dead) == 0
		assert info.id in state.processes

		# Cleanup
		proc = psutil.Process(info.pid)
		proc.terminate()
		proc.wait()


class TestCheckRestartNeeded:
	def test_check_restart_needed(self, state, temp_state_dir: Path):
		# Add a dead process with restart enabled
		dead_info = ProcessInfo(
			id=1,
			pid=99999,
			name="auto_restart",
			cmd="echo done",
			cwd="/tmp",
			restart=True,
			started_at="2024-01-01T00:00:00",
			stdout_log="/tmp/auto_restart.stdout.log",
			stderr_log="/tmp/auto_restart.stderr.log",
		)
		state.add_process(dead_info)

		# Mock start_process to return a new process with a different PID
		with patch("sentinel.process.start_process") as mock_start:
			new_info = ProcessInfo(
				id=2,
				pid=88888,
				name="auto_restart",
				cmd="echo done",
				cwd="/tmp",
				restart=True,
				started_at="2024-01-01T00:00:01",
				stdout_log="/tmp/auto_restart.stdout.log",
				stderr_log="/tmp/auto_restart.stderr.log",
			)
			mock_start.return_value = new_info

			# Mock psutil to say the dead process doesn't exist
			with patch("sentinel.process.psutil.pid_exists") as mock_pid_exists:
				mock_pid_exists.return_value = False

				restarted = check_restart_needed(state)

		assert len(restarted) == 1
		assert restarted[0].name == "auto_restart"
		assert restarted[0].restart is True
		assert 1 not in state.processes  # Old process removed

	def test_check_restart_not_needed(self, state, temp_state_dir: Path):
		info = start_process(state, "sleep 60", name="no_restart", restart=True)

		restarted = check_restart_needed(state)

		assert len(restarted) == 0
		assert info.id in state.processes
		assert psutil.pid_exists(info.pid)

		# Cleanup
		proc = psutil.Process(info.pid)
		proc.terminate()
		proc.wait()

	def test_check_restart_disabled(self, state, temp_state_dir: Path):
		info = start_process(state, "echo 'done'", name="no_restart", restart=False)

		# Wait for process to finish
		time.sleep(0.5)

		restarted = check_restart_needed(state)

		assert len(restarted) == 0
		# Process should still be in state (not automatically cleaned up)
		assert info.id in state.processes
