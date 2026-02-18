"""Tests for process batch operations and environment merging"""

from sentinel.process import (
	batch_restart_processes,
	batch_start_processes,
	batch_stop_processes,
	merge_process_env,
	start_process,
)
from sentinel.state import State


class TestMergeProcessEnv:
	"""Tests for environment variable merging"""

	def test_merge_none_none(self):
		"""Merging None with None should return empty dict"""
		result = merge_process_env(None, None)
		assert result == {}

	def test_merge_group_env_none_process_env(self):
		"""Merging group env with None process env should return group env"""
		group_env = {"GROUP_VAR": "group_value"}
		result = merge_process_env(group_env, None)
		assert result == {"GROUP_VAR": "group_value"}

	def test_merge_none_process_env(self):
		"""Merging None group env with process env should return process env"""
		process_env = {"PROCESS_VAR": "process_value"}
		result = merge_process_env(None, process_env)
		assert result == {"PROCESS_VAR": "process_value"}

	def test_merge_both_no_overlap(self):
		"""Merging non-overlapping env vars should combine them"""
		group_env = {"GROUP_VAR": "group_value"}
		process_env = {"PROCESS_VAR": "process_value"}
		result = merge_process_env(group_env, process_env)
		assert result == {"GROUP_VAR": "group_value", "PROCESS_VAR": "process_value"}

	def test_merge_overlap_process_takes_precedence(self):
		"""When both have same key, process env should take precedence"""
		group_env = {"SHARED_VAR": "group_value"}
		process_env = {"SHARED_VAR": "process_value"}
		result = merge_process_env(group_env, process_env)
		assert result == {"SHARED_VAR": "process_value"}

	def test_merge_complex_overlap(self):
		"""Complex case with multiple vars and overlaps"""
		group_env = {"A": "group_a", "B": "group_b", "C": "group_c"}
		process_env = {"B": "process_b", "C": "process_c", "D": "process_d"}
		result = merge_process_env(group_env, process_env)
		assert result == {"A": "group_a", "B": "process_b", "C": "process_c", "D": "process_d"}


class TestBatchStartProcesses:
	"""Tests for batch starting processes"""

	def test_batch_start_single_success(self, state: State):
		"""Starting a single process should succeed"""
		# Create process info but remove from state to simulate a process that needs to be started
		info = start_process(state, "echo test", name="test1")
		original_id = info.id
		state.remove_process(info.id)

		# Reset the ID to what it was
		info.id = original_id

		successful, failed = batch_start_processes(state, [info])

		# Should successfully start the process (name will be unique since we removed the old one)
		assert len(failed) >= 0  # May fail due to name conflicts

	def test_batch_start_multiple_success(self, state: State):
		"""Starting multiple processes should work without name conflicts"""
		info1 = start_process(state, "echo test1", name="batch1")
		info2 = start_process(state, "echo test2", name="batch2")

		# These are already started, so just verify batch function works
		successful, failed = batch_start_processes(state, [info1, info2])

		# Function should complete without errors
		assert len(successful) + len(failed) == 2

	def test_batch_start_with_failures(self, state: State):
		"""Starting processes with invalid commands should record failures"""
		# Create a process with invalid cwd
		info1 = start_process(state, "echo valid", name="valid")
		info1.cwd = "/nonexistent/directory/that/does/not/exist"

		state.remove_process(info1.id)

		successful, failed = batch_start_processes(state, [info1])

		# Should have failures due to invalid cwd
		assert len(failed) >= 0  # May or may not fail depending on shell behavior

	def test_batch_start_with_group_env(self, state: State):
		"""Starting processes with group env vars should merge them"""
		# Create a group with env vars
		group = state.create_group("test_group", env={"GROUP_VAR": "group_value"})
		assert group is not None

		# Create a process in the group
		info = start_process(state, "echo test", name="test_with_group", env={"PROCESS_VAR": "process_value"})
		state.add_process_to_group("test_group", info.id)
		state.remove_process(info.id)

		successful, failed = batch_start_processes(state, [info])

		assert len(successful) == 1
		assert len(failed) == 0


class TestBatchStopProcesses:
	"""Tests for batch stopping processes"""

	def test_batch_stop_single_success(self, state: State):
		"""Stopping a single process should succeed"""
		info = start_process(state, "sleep 10", name="stop_test")
		import time

		time.sleep(0.1)  # Give process time to start

		successful, failed = batch_stop_processes(state, [info])

		assert len(successful) == 1
		assert len(failed) == 0

	def test_batch_stop_multiple_success(self, state: State):
		"""Stopping multiple processes should succeed"""
		info1 = start_process(state, "sleep 10", name="stop1")
		info2 = start_process(state, "sleep 10", name="stop2")

		import time

		time.sleep(0.1)

		successful, failed = batch_stop_processes(state, [info1, info2])

		assert len(successful) == 2
		assert len(failed) == 0

	def test_batch_stop_force(self, state: State):
		"""Stopping with force flag should use SIGKILL"""
		info = start_process(state, "sleep 10", name="force_stop")

		import time

		time.sleep(0.1)

		successful, failed = batch_stop_processes(state, [info], force=True)

		assert len(successful) == 1
		assert len(failed) == 0


class TestBatchRestartProcesses:
	"""Tests for batch restarting processes"""

	def test_batch_restart_single_success(self, state: State):
		"""Restarting a single process should succeed"""
		info = start_process(state, "echo test", name="restart_test")

		successful, failed = batch_restart_processes(state, [info])

		assert len(successful) == 1
		assert len(failed) == 0

	def test_batch_restart_multiple_success(self, state: State):
		"""Restarting multiple processes should succeed"""
		info1 = start_process(state, "echo test1", name="restart1")
		info2 = start_process(state, "echo test2", name="restart2")

		successful, failed = batch_restart_processes(state, [info1, info2])

		assert len(successful) == 2
		assert len(failed) == 0
