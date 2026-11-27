"""Tests for dashboard data collection"""

from collections.abc import Callable

import pytest

import sentinel_web.data as dashboard_data
from sentinel_core.metrics import ProcessMetrics
from sentinel_core.models import ProcessInfo
from sentinel_core.process import stop_process
from sentinel_core.state import State
from sentinel_web.data import collect_dashboard_data


class TestCollectDashboardData:
	def test_empty_state_reports_no_processes(self, state: State) -> None:
		data = collect_dashboard_data(state)

		assert data["processes"] == []
		assert data["updated_at"]

	def test_rows_carry_metrics_and_cluster_fields(
		self, state: State, spawn_process: Callable[..., ProcessInfo]
	) -> None:
		spawn_process("sleep 30", name="web-1", cluster="web", cluster_index=1)

		data = collect_dashboard_data(state)

		(row,) = data["processes"]
		assert row["name"] == "web-1"
		assert row["running"] is True
		assert row["cluster"] == "web"
		assert row["cluster_index"] == 1
		assert row["group"] is None
		assert row["cpu_percent"] >= 0
		assert row["memory_mb"] >= 0
		assert row["uptime_seconds"] >= 0

	def test_rows_mark_stopped_processes(self, state: State, spawn_process: Callable[..., ProcessInfo]) -> None:
		info = spawn_process("sleep 30", name="sleeper")
		stop_process(state, info.id)

		data = collect_dashboard_data(state)

		(row,) = data["processes"]
		assert row["running"] is False
		assert row["status"] == "stopped"


class TestDashboardRowLabels:
	def test_rows_carry_the_group(self, state: State, spawn_process: Callable[..., ProcessInfo]) -> None:
		state.create_group("staff")
		info = spawn_process("sleep 30", name="grouped")
		state.add_process_to_group("staff", info.id)

		(row,) = collect_dashboard_data(state)["processes"]

		assert row["group"] == "staff"

	def test_rows_without_a_record_become_empty_labels(self, state: State, monkeypatch: pytest.MonkeyPatch) -> None:
		orphan = ProcessMetrics(
			id=99,
			name="orphan",
			pid=1,
			status="running",
			running=True,
			cpu_percent=0.0,
			memory_mb=0.0,
			uptime_seconds=0.0,
		)
		monkeypatch.setattr(dashboard_data, "collect_metrics", lambda _: [orphan])

		(row,) = collect_dashboard_data(state)["processes"]

		assert row["group"] is None
		assert row["cluster"] is None
		assert row["cluster_index"] is None
