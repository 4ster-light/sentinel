"""Tests for process group management"""

import pytest

from sentinel.process import start_process
from sentinel.state import GroupInfo, State


class TestGroupInfo:
	"""Tests for GroupInfo dataclass"""

	def test_to_dict(self):
		"""GroupInfo should convert to dictionary"""
		group = GroupInfo(name="test_group", created_at="2025-01-18T00:00:00", env={"KEY": "VALUE"})
		result = group.to_dict()

		assert result == {
			"name": "test_group",
			"created_at": "2025-01-18T00:00:00",
			"env": {"KEY": "VALUE"},
			"env_file": None,
		}

	def test_to_dict_no_env(self):
		"""GroupInfo should handle empty env"""
		group = GroupInfo(name="test_group", created_at="2025-01-18T00:00:00")
		result = group.to_dict()

		assert result == {
			"name": "test_group",
			"created_at": "2025-01-18T00:00:00",
			"env": {},
			"env_file": None,
		}

	def test_from_dict(self):
		"""GroupInfo should be created from dictionary"""
		data = {
			"name": "test_group",
			"created_at": "2025-01-18T00:00:00",
			"env": {"KEY": "VALUE"},
		}
		group = GroupInfo.from_dict(data)

		assert group.name == "test_group"
		assert group.created_at == "2025-01-18T00:00:00"
		assert group.env == {"KEY": "VALUE"}

	def test_from_dict_no_env(self):
		"""GroupInfo should handle missing env in dict"""
		data = {
			"name": "test_group",
			"created_at": "2025-01-18T00:00:00",
		}
		group = GroupInfo.from_dict(data)

		assert group.name == "test_group"
		assert group.env == {}


class TestStateGroupOperations:
	"""Tests for State group management methods"""

	def test_create_group(self, state: State):
		"""Creating a group should succeed"""
		group = state.create_group("test_group")

		assert group is not None
		assert group.name == "test_group"
		assert group.env == {}

	def test_create_group_with_env(self, state: State):
		"""Creating a group with env vars should work"""
		env = {"KEY1": "VALUE1", "KEY2": "VALUE2"}
		group = state.create_group("test_group", env=env)

		assert group is not None
		assert group.env == env

	def test_create_duplicate_group(self, state: State):
		"""Creating a duplicate group should fail"""
		state.create_group("test_group")
		result = state.create_group("test_group")

		assert result is None

	def test_get_group(self, state: State):
		"""Getting a group should return it"""
		created = state.create_group("test_group")
		retrieved = state.get_group("test_group")

		assert retrieved is not None
		assert retrieved.name == created.name

	def test_get_nonexistent_group(self, state: State):
		"""Getting a nonexistent group should return None"""
		result = state.get_group("nonexistent")

		assert result is None

	def test_remove_group(self, state: State):
		"""Removing a group should succeed"""
		state.create_group("test_group")
		result = state.remove_group("test_group")

		assert result is True
		assert state.get_group("test_group") is None

	def test_remove_nonexistent_group(self, state: State):
		"""Removing a nonexistent group should return False"""
		result = state.remove_group("nonexistent")

		assert result is False

	def test_remove_group_unassigns_processes(self, state: State):
		"""Removing a group should unassign all processes"""
		state.create_group("test_group")
		info = start_process(state, "echo test", name="test_process")
		state.add_process_to_group("test_group", info.id)

		state.remove_group("test_group")

		process = state.get_process(info.id)
		assert process.group is None

	def test_add_process_to_group(self, state: State):
		"""Adding a process to a group should succeed"""
		state.create_group("test_group")
		info = start_process(state, "echo test", name="test_process")

		result = state.add_process_to_group("test_group", info.id)

		assert result is True
		process = state.get_process(info.id)
		assert process.group == "test_group"

	def test_add_process_to_nonexistent_group(self, state: State):
		"""Adding a process to a nonexistent group should fail"""
		info = start_process(state, "echo test", name="test_process")
		result = state.add_process_to_group("nonexistent", info.id)

		assert result is False

	def test_add_nonexistent_process_to_group(self, state: State):
		"""Adding a nonexistent process to a group should fail"""
		state.create_group("test_group")
		result = state.add_process_to_group("test_group", 9999)

		assert result is False

	def test_move_process_to_different_group(self, state: State):
		"""Moving a process from one group to another should work"""
		state.create_group("group1")
		state.create_group("group2")
		info = start_process(state, "echo test", name="test_process")

		state.add_process_to_group("group1", info.id)
		process = state.get_process(info.id)
		assert process.group == "group1"

		state.add_process_to_group("group2", info.id)
		process = state.get_process(info.id)
		assert process.group == "group2"

	def test_remove_process_from_group(self, state: State):
		"""Removing a process from a group should succeed"""
		state.create_group("test_group")
		info = start_process(state, "echo test", name="test_process")
		state.add_process_to_group("test_group", info.id)

		result = state.remove_process_from_group(info.id)

		assert result is True
		process = state.get_process(info.id)
		assert process.group is None

	def test_remove_nonexistent_process_from_group(self, state: State):
		"""Removing a nonexistent process should fail"""
		result = state.remove_process_from_group(9999)

		assert result is False

	def test_list_groups(self, state: State):
		"""Listing groups should return all groups"""
		state.create_group("group1")
		state.create_group("group2")

		groups = state.list_groups()

		assert len(groups) == 2
		names = [g.name for g in groups]
		assert "group1" in names
		assert "group2" in names

	def test_list_groups_empty(self, state: State):
		"""Listing groups when none exist should return empty list"""
		groups = state.list_groups()

		assert groups == []

	def test_get_processes_in_group(self, state: State):
		"""Getting processes in a group should return them"""
		state.create_group("test_group")
		info1 = start_process(state, "echo test1", name="proc1")
		info2 = start_process(state, "echo test2", name="proc2")

		state.add_process_to_group("test_group", info1.id)
		state.add_process_to_group("test_group", info2.id)

		processes = state.get_processes_in_group("test_group")

		assert len(processes) == 2
		names = [p.name for p in processes]
		assert "proc1" in names
		assert "proc2" in names

	def test_get_processes_in_empty_group(self, state: State):
		"""Getting processes in an empty group should return empty list"""
		state.create_group("test_group")
		processes = state.get_processes_in_group("test_group")

		assert processes == []

	def test_get_processes_in_nonexistent_group(self, state: State):
		"""Getting processes in nonexistent group should return empty list"""
		processes = state.get_processes_in_group("nonexistent")

		assert processes == []

	def test_group_persistence(self, state: State, temp_state_dir):
		"""Groups should persist across State instances"""
		state.create_group("test_group")
		info = start_process(state, "echo test", name="test_process")
		state.add_process_to_group("test_group", info.id)

		# Create new state instance (should load from file)
		state2 = State()

		group = state2.get_group("test_group")
		assert group is not None
		assert group.name == "test_group"

		process = state2.get_process(info.id)
		assert process.group == "test_group"
