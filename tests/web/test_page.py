"""Tests for the dashboard page markup"""

from sentinel_web.page import DASHBOARD_PAGE


class TestDashboardPage:
	def test_is_self_contained_and_polls_data(self) -> None:
		assert DASHBOARD_PAGE.startswith("<!DOCTYPE html>")
		assert "/api/processes" in DASHBOARD_PAGE
		assert "src=" not in DASHBOARD_PAGE
		assert "<link" not in DASHBOARD_PAGE
