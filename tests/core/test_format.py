"""Tests for shared formatting helpers"""

from sentinel_core.format import format_memory_mb, format_uptime_seconds, uptime_from_started_at


class TestFormatUptimeSeconds:
	def test_seconds(self):
		assert format_uptime_seconds(42) == "42s"

	def test_minutes(self):
		assert format_uptime_seconds(303) == "5m 3s"

	def test_hours(self):
		assert format_uptime_seconds(7322) == "2h 2m"

	def test_days(self):
		assert format_uptime_seconds(90061) == "1d 1h"


class TestFormatMemoryMb:
	def test_kb(self):
		assert format_memory_mb(0.5) == "512KB"

	def test_mb(self):
		assert format_memory_mb(45.26) == "45.3MB"

	def test_gb(self):
		assert format_memory_mb(2048.0) == "2.00GB"


class TestUptimeFromStartedAt:
	def test_zero_for_now(self):
		assert uptime_from_started_at("2024-01-01T00:00:00") >= 0.0

	def test_invalid_returns_zero(self):
		assert uptime_from_started_at("not-a-date") == 0.0
