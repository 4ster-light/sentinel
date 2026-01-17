"""Tests for CLI group commands"""

import pytest
from typer.testing import CliRunner

from sentinel.cli import app
from sentinel.process import start_process
from sentinel.state import State

runner = CliRunner()


class TestGroupCommands:
	"""Tests for group management commands"""

	def test_group_create_command(self, state: State):
		"""Test creating a group"""
		result = runner.invoke(app, ["group", "create", "testgroup"])
		assert result.exit_code == 0
		assert "Created" in result.stdout
		assert "testgroup" in result.stdout

	def test_group_create_with_env(self, state: State):
		"""Test creating a group with env vars"""
		result = runner.invoke(
			app,
			["group", "create", "testgroup", "--env", "VAR1=value1", "--env", "VAR2=value2"],
		)
		assert result.exit_code == 0
		assert "Created" in result.stdout

	def test_group_create_duplicate(self, state: State):
		"""Test creating duplicate group fails"""
		runner.invoke(app, ["group", "create", "testgroup"])
		result = runner.invoke(app, ["group", "create", "testgroup"])
		assert result.exit_code != 0

	def test_group_list_empty(self):
		"""Test listing groups when none exist"""
		result = runner.invoke(app, ["group", "list"])
		assert result.exit_code == 0
		assert "No groups" in result.stdout or "GROUP" in result.stdout

	def test_group_list_with_groups(self, state: State):
		"""Test listing groups"""
		state.create_group("group1")
		state.create_group("group2")

		result = runner.invoke(app, ["group", "list"])
		assert result.exit_code == 0
		assert "group1" in result.stdout or "group2" in result.stdout

	def test_group_list_specific(self, state: State):
		"""Test listing specific group"""
		state.create_group("testgroup")
		info = start_process(state, "echo test", name="proc1")
		state.add_process_to_group("testgroup", info.id)

		result = runner.invoke(app, ["group", "list", "testgroup"])
		assert result.exit_code == 0
		assert "testgroup" in result.stdout
		assert "proc1" in result.stdout

	def test_group_list_nonexistent(self):
		"""Test listing nonexistent group"""
		result = runner.invoke(app, ["group", "list", "nonexistent"])
		assert result.exit_code != 0

	def test_group_add_process(self, state: State):
		"""Test adding process to group"""
		state.create_group("testgroup")
		info = start_process(state, "echo test", name="proc1")

		result = runner.invoke(app, ["group", "add", "testgroup", str(info.id)])
		assert result.exit_code == 0
		assert "Added" in result.stdout

	def test_group_add_nonexistent_group(self, state: State):
		"""Test adding to nonexistent group fails"""
		info = start_process(state, "echo test", name="proc1")
		result = runner.invoke(app, ["group", "add", "nonexistent", str(info.id)])
		assert result.exit_code != 0

	def test_group_add_nonexistent_process(self, state: State):
		"""Test adding nonexistent process fails"""
		state.create_group("testgroup")
		result = runner.invoke(app, ["group", "add", "testgroup", "9999"])
		assert result.exit_code != 0

	def test_group_remove_process(self, state: State):
		"""Test removing process from group"""
		state.create_group("testgroup")
		info = start_process(state, "echo test", name="proc1")
		state.add_process_to_group("testgroup", info.id)

		result = runner.invoke(app, ["group", "remove", str(info.id)])
		assert result.exit_code == 0
		assert "Removed" in result.stdout

	def test_group_remove_nonexistent_process(self):
		"""Test removing nonexistent process fails"""
		result = runner.invoke(app, ["group", "remove", "9999"])
		assert result.exit_code != 0

	def test_group_start(self, state: State):
		"""Test starting group processes"""
		state.create_group("testgroup")
		info1 = start_process(state, "echo test1", name="proc1")
		info2 = start_process(state, "echo test2", name="proc2")
		state.add_process_to_group("testgroup", info1.id)
		state.add_process_to_group("testgroup", info2.id)

		# Remove from state to simulate need to start
		state.remove_process(info1.id)
		state.remove_process(info2.id)

		result = runner.invoke(app, ["group", "start", "testgroup"])
		assert result.exit_code == 0

	def test_group_start_nonexistent(self):
		"""Test starting nonexistent group fails"""
		result = runner.invoke(app, ["group", "start", "nonexistent"])
		assert result.exit_code != 0

	def test_group_stop(self, state: State):
		"""Test stopping group processes"""
		state.create_group("testgroup")
		info1 = start_process(state, "sleep 10", name="proc1")
		info2 = start_process(state, "sleep 10", name="proc2")
		state.add_process_to_group("testgroup", info1.id)
		state.add_process_to_group("testgroup", info2.id)

		result = runner.invoke(app, ["group", "stop", "testgroup"])
		assert result.exit_code == 0

	def test_group_stop_nonexistent(self):
		"""Test stopping nonexistent group fails"""
		result = runner.invoke(app, ["group", "stop", "nonexistent"])
		assert result.exit_code != 0

	def test_group_restart(self, state: State):
		"""Test restarting group processes"""
		state.create_group("testgroup")
		info1 = start_process(state, "echo test1", name="proc1")
		info2 = start_process(state, "echo test2", name="proc2")
		state.add_process_to_group("testgroup", info1.id)
		state.add_process_to_group("testgroup", info2.id)

		result = runner.invoke(app, ["group", "restart", "testgroup"])
		assert result.exit_code == 0

	def test_group_delete(self, state: State):
		"""Test deleting a group"""
		state.create_group("testgroup")

		result = runner.invoke(app, ["group", "delete", "testgroup"])
		assert result.exit_code == 0
		assert "Deleted" in result.stdout

	def test_group_delete_nonexistent(self):
		"""Test deleting nonexistent group fails"""
		result = runner.invoke(app, ["group", "delete", "nonexistent"])
		assert result.exit_code != 0

	def test_group_delete_with_processes(self, state: State):
		"""Test deleting group with --with-processes"""
		state.create_group("testgroup")
		info1 = start_process(state, "sleep 10", name="proc1")
		state.add_process_to_group("testgroup", info1.id)

		result = runner.invoke(app, ["group", "delete", "testgroup", "--with-processes"])
		assert result.exit_code == 0
		assert "Deleted" in result.stdout
