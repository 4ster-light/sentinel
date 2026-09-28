"""Tests for CLI state loading behavior"""

from pathlib import Path

from typer.testing import CliRunner

from sentinel_cli import app

runner = CliRunner()


class TestCorruptStateSurfacing:
	def test_list_warns_on_corrupt_state(self, temp_state_dir: Path):
		state_file = temp_state_dir / ".sentinel" / "state.json"
		state_file.write_text("{this is not json")

		result = runner.invoke(app, ["list"])

		assert result.exit_code == 0
		assert "corrupt" in result.stdout.lower()
		assert "No processes running" in result.stdout
		assert list((temp_state_dir / ".sentinel").glob("state.json.corrupt-*"))

	def test_status_warns_on_corrupt_state(self, temp_state_dir: Path):
		state_file = temp_state_dir / ".sentinel" / "state.json"
		state_file.write_text("[1, 2, 3]")

		result = runner.invoke(app, ["status", "1"])

		assert "corrupt" in result.stdout.lower()
		assert "Process not found" in result.stdout
