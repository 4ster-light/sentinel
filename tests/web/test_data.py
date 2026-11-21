"""Tests for dashboard data collection"""

from collections.abc import Callable

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
