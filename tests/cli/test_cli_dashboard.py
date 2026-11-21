"""Tests for the dashboard command"""

import socket
from typing import Any

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import sentinel_cli.dashboard as dashboard_module
from sentinel_cli import app
from sentinel_core.state import State

runner = CliRunner()


class TestDashboardCommand:
	def test_dashboard_rejects_invalid_port(self, state: State) -> None:
		result = runner.invoke(app, ["dashboard", "--port", "0"])

		assert result.exit_code != 0
		assert "between 1 and 65535" in result.stdout

	def test_dashboard_wires_the_app_and_serves(self, state: State, monkeypatch: pytest.MonkeyPatch) -> None:
		served: dict[str, Any] = {}

		def fake_run(app_object: object, host: str, port: int, log_level: str) -> None:
			served["app"] = app_object
			served["host"] = host
			served["port"] = port
			served["log_level"] = log_level

		monkeypatch.setattr(dashboard_module, "_check_bind", lambda host, port: None)
		monkeypatch.setattr(dashboard_module.uvicorn, "run", fake_run)

		result = runner.invoke(app, ["dashboard", "--port", "7331"])

		assert result.exit_code == 0, result.output
		assert served["host"] == "127.0.0.1"
		assert served["port"] == 7331
		assert served["log_level"] == "warning"
		assert "http://127.0.0.1:7331/" in result.stdout
		assert "Stopped dashboard server" in result.stdout
		client = TestClient(served["app"])
		assert client.get("/api/processes").status_code == 200

	def test_dashboard_reports_an_unbindable_port(self, state: State, require_sockets: None) -> None:
		with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as taken:
			taken.bind(("127.0.0.1", 0))
			port = taken.getsockname()[1]

			result = runner.invoke(app, ["dashboard", "--port", str(port)])

		assert result.exit_code != 0
		assert "Cannot bind" in result.stdout
