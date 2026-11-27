"""Tests for the dashboard control endpoints"""

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sse import read_events

from sentinel_core.cluster import cluster_members
from sentinel_core.models import ProcessInfo
from sentinel_core.process import get_process_status, stop_process
from sentinel_core.state import State
from sentinel_web import create_dashboard_app


@pytest.fixture
def control_client(state: State) -> TestClient:
	return TestClient(create_dashboard_app(lambda: state))


@pytest.fixture
def token_client(state: State) -> Iterator[TestClient]:
	with TestClient(create_dashboard_app(lambda: state, control_token="s3cret")) as client:
		yield client


class TestControlEndpoints:
	def test_stop_marks_the_process_stopped(
		self, control_client: TestClient, state: State, spawn_process: Callable[..., ProcessInfo]
	) -> None:
		info = spawn_process("sleep 60", name="web-1")

		response = control_client.post(f"/api/processes/{info.id}/stop")

		assert response.status_code == 200
		assert response.json() == {"message": "Stopped web-1"}
		stopped = state.get_process(info.id)
		assert stopped is not None
		assert stopped.stopped is True

	def test_start_runs_a_stopped_process(
		self, control_client: TestClient, state: State, spawn_process: Callable[..., ProcessInfo]
	) -> None:
		info = spawn_process("sleep 60", name="sleeper")
		stop_process(state, info.id)

		response = control_client.post(f"/api/processes/{info.id}/start")

		assert response.status_code == 200
		assert response.json() == {"message": "Started sleeper"}
		started = state.get_process(info.id)
		assert started is not None
		assert started.stopped is False
		assert get_process_status(started).running

	def test_start_refuses_a_running_process(
		self, control_client: TestClient, spawn_process: Callable[..., ProcessInfo]
	) -> None:
		info = spawn_process("sleep 60", name="busy")

		response = control_client.post(f"/api/processes/{info.id}/start")

		assert response.status_code == 400
		assert response.json()["detail"] == "Process 'busy' is already running"

	def test_restart_replaces_the_process(
		self, control_client: TestClient, state: State, spawn_process: Callable[..., ProcessInfo]
	) -> None:
		info = spawn_process("sleep 60", name="worker")

		response = control_client.post(f"/api/processes/{info.id}/restart")

		assert response.status_code == 200
		assert response.json() == {"message": "Restarted worker"}
		restarted = state.get_process(info.id)
		assert restarted is not None
		assert restarted.pid != info.pid
		assert get_process_status(restarted).running

	def test_scale_up_grows_the_cluster(
		self, control_client: TestClient, state: State, spawn_process: Callable[..., ProcessInfo]
	) -> None:
		spawn_process("sleep 60", name="web-1", cluster="web", cluster_index=1, cluster_min=1, cluster_max=3)

		response = control_client.post("/api/clusters/web/scale", json={"direction": "up"})

		assert response.status_code == 200
		assert response.json() == {"message": "Scaled web to 2 instances"}
		assert len(cluster_members(state, "web")) == 2

	def test_scale_down_shrinks_the_cluster(
		self, control_client: TestClient, state: State, spawn_process: Callable[..., ProcessInfo]
	) -> None:
		spawn_process("sleep 60", name="web-1", cluster="web", cluster_index=1, cluster_min=1, cluster_max=3)
		spawn_process("sleep 60", name="web-2", cluster="web", cluster_index=2, cluster_min=1, cluster_max=3)

		response = control_client.post("/api/clusters/web/scale", json={"direction": "down"})

		assert response.status_code == 200
		assert response.json() == {"message": "Scaled web to 1 instances"}
		assert len(cluster_members(state, "web")) == 1

	def test_scale_beyond_the_range_reports_the_core_error(
		self, control_client: TestClient, spawn_process: Callable[..., ProcessInfo]
	) -> None:
		spawn_process("sleep 60", name="web-1", cluster="web", cluster_index=1, cluster_min=1, cluster_max=2)
		control_client.post("/api/clusters/web/scale", json={"direction": "up"})

		response = control_client.post("/api/clusters/web/scale", json={"direction": "up"})

		assert response.status_code == 400
		assert response.json()["detail"] == "Cluster 'web' allows 1-2 instances, not 3"

	def test_scale_rejects_unknown_directions(
		self, control_client: TestClient, spawn_process: Callable[..., ProcessInfo]
	) -> None:
		spawn_process("sleep 60", name="web-1", cluster="web", cluster_index=1, cluster_min=1, cluster_max=3)

		response = control_client.post("/api/clusters/web/scale", json={"direction": "sideways"})

		assert response.status_code == 422

	def test_unknown_process_reports_404(self, control_client: TestClient) -> None:
		assert control_client.post("/api/processes/999/stop").status_code == 404
		assert control_client.post("/api/processes/999/restart").status_code == 404
		assert control_client.post("/api/processes/999/start").status_code == 404

	def test_unknown_cluster_reports_404(self, control_client: TestClient) -> None:
		response = control_client.post("/api/clusters/ghost/scale", json={"direction": "up"})

		assert response.status_code == 404
		assert response.json()["detail"] == "Unknown cluster 'ghost'"


class TestControlToken:
	@pytest.mark.parametrize(
		"path",
		["/api/processes/1/stop", "/api/processes/1/restart", "/api/processes/1/start", "/api/clusters/web/scale"],
	)
	def test_every_control_route_requires_the_token(self, token_client: TestClient, path: str) -> None:
		body = {"direction": "up"} if path.endswith("/scale") else None

		response = token_client.post(path, json=body)

		assert response.status_code == 401
		assert response.json()["detail"] == "Control requires a valid token"

	def test_a_wrong_token_is_refused(
		self, token_client: TestClient, spawn_process: Callable[..., ProcessInfo]
	) -> None:
		info = spawn_process("sleep 60", name="web-1")

		response = token_client.post(f"/api/processes/{info.id}/stop", headers={"X-Control-Token": "nope"})

		assert response.status_code == 401

	def test_a_valid_token_unlocks_control(
		self, token_client: TestClient, state: State, spawn_process: Callable[..., ProcessInfo]
	) -> None:
		info = spawn_process("sleep 60", name="web-1")

		response = token_client.post(f"/api/processes/{info.id}/stop", headers={"X-Control-Token": "s3cret"})

		assert response.status_code == 200
		stopped = state.get_process(info.id)
		assert stopped is not None
		assert stopped.stopped is True

	def test_reading_needs_no_token(self, state: State, token_client: TestClient) -> None:
		assert token_client.get("/").status_code == 200
		assert token_client.get("/api/processes").status_code == 200

		app = create_dashboard_app(lambda: state, control_token="s3cret")
		start, _events = read_events(app, count=1)

		assert start["status"] == 200


class TestControlDetails:
	def test_unknown_process_reports_the_exact_detail(self, control_client: TestClient) -> None:
		response = control_client.post("/api/processes/999/stop")

		assert response.status_code == 404
		assert response.json()["detail"] == "Process not found: 999"

	def test_a_placeholder_token_still_needs_a_header(self, state: State) -> None:
		with TestClient(create_dashboard_app(lambda: state, control_token="XXXX")) as client:
			response = client.post("/api/processes/1/stop")

		assert response.status_code == 401
		assert response.json()["detail"] == "Control requires a valid token"
