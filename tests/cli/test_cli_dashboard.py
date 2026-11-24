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

	def test_dashboard_refuses_a_non_loopback_bind_without_a_token(
		self, state: State, monkeypatch: pytest.MonkeyPatch
	) -> None:
		served: dict[str, Any] = {}

		def fail_run(*args: object, **kwargs: object) -> None:
			served["called"] = True

		monkeypatch.setattr(dashboard_module, "_check_bind", lambda host, port: None)
		monkeypatch.setattr(dashboard_module.uvicorn, "run", fail_run)

		result = runner.invoke(app, ["dashboard", "--host", "0.0.0.0"])

		assert result.exit_code != 0
		assert "requires --control-token" in result.stdout
		assert "called" not in served

	def test_dashboard_serves_a_non_loopback_bind_with_a_token(
		self, state: State, monkeypatch: pytest.MonkeyPatch
	) -> None:
		served: dict[str, Any] = {}

		def fake_run(app_object: object, host: str, port: int, log_level: str) -> None:
			served["app"] = app_object
			served["host"] = host

		monkeypatch.setattr(dashboard_module, "_check_bind", lambda host, port: None)
		monkeypatch.setattr(dashboard_module.uvicorn, "run", fake_run)

		result = runner.invoke(app, ["dashboard", "--host", "0.0.0.0", "--control-token", "s3cret"])

		assert result.exit_code == 0, result.output
		assert served["host"] == "0.0.0.0"
		client = TestClient(served["app"])
		assert client.post("/api/processes/1/stop").status_code == 401
		assert client.post("/api/processes/1/stop", headers={"X-Control-Token": "s3cret"}).status_code == 404

	@pytest.mark.parametrize(
		("host", "expected"),
		[
			("127.0.0.1", True),
			("localhost", True),
			("::1", True),
			("0.0.0.0", False),
			("192.168.1.5", False),
			("dash.example", False),
		],
	)
	def test_is_loopback_classifies_hosts(self, host: str, expected: bool) -> None:
		assert dashboard_module._is_loopback(host) is expected
