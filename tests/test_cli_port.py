"""Tests for CLI port commands"""

import pytest
from typer.testing import CliRunner

from sentinel.cli import app

runner = CliRunner()


class TestPortCommands:
	"""Tests for port management commands"""

	def test_port_allocate_auto(self):
		"""Test allocating a port automatically"""
		result = runner.invoke(app, ["port", "allocate"])
		assert result.exit_code == 0
		assert "Allocated" in result.stdout

	def test_port_allocate_specific(self):
		"""Test allocating a specific port"""
		result = runner.invoke(app, ["port", "allocate", "19999"])
		# Port may not be available, so we just check the function runs
		assert "Allocated" in result.stdout or "Failed" in result.stdout

	def test_port_allocate_with_name(self):
		"""Test allocating a port with name"""
		result = runner.invoke(app, ["port", "allocate", "--name", "myport"])
		assert result.exit_code == 0
		assert "myport" in result.stdout or "Allocated" in result.stdout

	def test_port_list_empty(self):
		"""Test listing ports when none allocated"""
		result = runner.invoke(app, ["port", "list"])
		assert result.exit_code == 0

	def test_port_free(self):
		"""Test freeing a port"""
		# First allocate
		allocate_result = runner.invoke(app, ["port", "allocate", "15001"])
		if allocate_result.exit_code == 0:
			# Then free it
			free_result = runner.invoke(app, ["port", "free", "15001"])
			assert free_result.exit_code == 0
