"""Tests for the FastAPI dashboard app"""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from sentinel_core.models import ProcessInfo
from sentinel_core.state import State
from sentinel_web import create_dashboard_app


@pytest.fixture
def client(state: State) -> TestClient:
	return TestClient(create_dashboard_app(lambda: state))


class TestDashboardApp:
	def test_serves_the_page(self, client: TestClient) -> None:
		response = client.get("/")

		assert response.status_code == 200
		assert response.headers["content-type"].startswith("text/html")
		assert "<!DOCTYPE html>" in response.text
		assert "/static/dashboard.css" in response.text
		assert "/static/dashboard.js" in response.text

	def test_serves_process_data(self, client: TestClient) -> None:
		response = client.get("/api/processes")

		assert response.status_code == 200
		assert response.headers["content-type"].startswith("application/json")
		payload = response.json()
		assert payload["processes"] == []
		assert payload["updated_at"]

	def test_reports_spawned_process(self, client: TestClient, spawn_process: Callable[..., ProcessInfo]) -> None:
		spawn_process("sleep 30", name="webproc", cluster="web", cluster_index=1)

		payload = client.get("/api/processes").json()

		(row,) = payload["processes"]
		assert row["name"] == "webproc"
		assert row["running"] is True
		assert row["cluster"] == "web"
		assert row["group"] is None

	def test_serves_the_static_assets(self, client: TestClient) -> None:
		stylesheet = client.get("/static/dashboard.css")
		scripts = client.get("/static/dashboard.js")

		assert stylesheet.status_code == 200
		assert stylesheet.headers["content-type"].startswith("text/css")
		assert scripts.status_code == 200
		assert "javascript" in scripts.headers["content-type"]

	def test_unknown_path_returns_404(self, client: TestClient) -> None:
		assert client.get("/metrics").status_code == 404


class TestAppSettings:
	def test_sets_the_title_and_disables_the_docs(self, state: State) -> None:
		app = create_dashboard_app(lambda: state)

		assert app.title == "Sentinel dashboard"
		assert app.docs_url is None
		assert app.redoc_url is None
		assert app.openapi_url is None

	def test_mounts_the_static_assets_under_a_name(self, state: State) -> None:
		app = create_dashboard_app(lambda: state)

		names = [getattr(route, "name", None) for route in app.routes]

		assert "static" in names
