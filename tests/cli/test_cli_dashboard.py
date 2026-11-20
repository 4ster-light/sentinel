"""Tests for the dashboard command"""

import json
from collections.abc import Callable
from typing import cast

import pytest
from typer.testing import CliRunner

from sentinel_cli import app
from sentinel_core.process import start_process
from sentinel_core.state import State

runner = CliRunner()


class _StubDashboardServer:
	def __init__(self) -> None:
		self.server_address = ("127.0.0.1", 7331)
		self.served = False

	def __enter__(self) -> _StubDashboardServer:
		return self

	def __exit__(self, *exc: object) -> None:
		return None

	def serve_forever(self) -> None:
		self.served = True


def wire_stub_server(monkeypatch: pytest.MonkeyPatch, created: dict[str, object]) -> _StubDashboardServer:
	server = _StubDashboardServer()

	def fake_create(
		address: tuple[str, int],
		render_page: Callable[[], str],
		render_data: Callable[[], str],
	) -> _StubDashboardServer:
		created["address"] = address
		created["page"] = render_page
		created["data"] = render_data
		return server

	monkeypatch.setattr("sentinel_cli.dashboard.create_dashboard_server", fake_create)
	return server


class TestDashboardCommand:
	def test_dashboard_rejects_invalid_port(self, state: State) -> None:
		result = runner.invoke(app, ["dashboard", "--port", "0"])

		assert result.exit_code != 0
		assert "between 1 and 65535" in result.stdout

	def test_dashboard_wires_server_and_serves(self, state: State, monkeypatch: pytest.MonkeyPatch) -> None:
		created: dict[str, object] = {}
		server = wire_stub_server(monkeypatch, created)

		result = runner.invoke(app, ["dashboard", "--port", "7331"])

		assert result.exit_code == 0, result.output
		assert server.served is True
		assert created["address"] == ("127.0.0.1", 7331)
		assert "http://127.0.0.1:7331/" in result.stdout

	def test_dashboard_page_is_self_contained_and_polls_data(
		self, state: State, monkeypatch: pytest.MonkeyPatch
	) -> None:
		created: dict[str, object] = {}
		wire_stub_server(monkeypatch, created)
		result = runner.invoke(app, ["dashboard"])

		assert result.exit_code == 0, result.output
		page = cast(Callable[[], str], created["page"])()
		assert page.startswith("<!DOCTYPE html>")
		assert "/api/processes" in page
		assert "src=" not in page
		assert "<link" not in page

	def test_dashboard_data_reports_spawned_process(self, state: State, monkeypatch: pytest.MonkeyPatch) -> None:
		start_process(state, "sleep 10", name="dashproc")
		created: dict[str, object] = {}
		wire_stub_server(monkeypatch, created)
		result = runner.invoke(app, ["dashboard"])

		assert result.exit_code == 0, result.output
		data = cast(Callable[[], str], created["data"])()
		payload = json.loads(data)
		(row,) = payload["processes"]
		assert row["name"] == "dashproc"
		assert payload["updated_at"]

	def test_dashboard_data_is_empty_without_processes(self, state: State, monkeypatch: pytest.MonkeyPatch) -> None:
		created: dict[str, object] = {}
		wire_stub_server(monkeypatch, created)
		result = runner.invoke(app, ["dashboard"])

		assert result.exit_code == 0, result.output
		data = cast(Callable[[], str], created["data"])()
		assert json.loads(data)["processes"] == []
