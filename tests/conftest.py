"""Pytest configuration and shared fixtures"""

import pytest
import tempfile
from pathlib import Path

from sentinel.state import State


@pytest.fixture
def temp_state_dir(monkeypatch: pytest.MonkeyPatch):
	"""Create a temporary state directory for testing"""
	with tempfile.TemporaryDirectory() as tmpdir:
		temp_path = Path(tmpdir)
		state_dir = temp_path / ".sentinel"
		logs_dir = state_dir / "logs"
		state_dir.mkdir(parents=True, exist_ok=True)
		logs_dir.mkdir(parents=True, exist_ok=True)

		# Patch the state module constants
		monkeypatch.setattr("sentinel.state.STATE_DIR", state_dir)
		monkeypatch.setattr("sentinel.state.STATE_FILE", state_dir / "state.json")
		monkeypatch.setattr("sentinel.state.LOGS_DIR", logs_dir)

		yield temp_path


@pytest.fixture
def state(temp_state_dir: Path) -> State:
	"""Create a clean State instance for testing"""
	return State()


@pytest.fixture
def temp_logs_dir(tmp_path: Path) -> Path:
	"""Create a temporary logs directory for testing"""
	logs = tmp_path / "logs"
	logs.mkdir()
	return logs
