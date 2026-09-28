"""Tests for StartOptions validation and ionice parsing"""

import pytest

from sentinel_core.options import StartOptions, parse_ionice_spec
from sentinel_core.state import HealthCheckConfig


class TestParseIoniceSpec:
	def test_none_and_empty(self):
		assert parse_ionice_spec(None) == (None, None)
		assert parse_ionice_spec("") == (None, None)
		assert parse_ionice_spec("   ") == (None, None)

	def test_idle(self):
		assert parse_ionice_spec("idle") == ("idle", None)

	def test_best_effort(self):
		assert parse_ionice_spec("best-effort") == ("best_effort", None)
		assert parse_ionice_spec("best-effort:6") == ("best_effort", 6)

	def test_realtime(self):
		assert parse_ionice_spec("realtime") == ("realtime", None)
		assert parse_ionice_spec("realtime:0") == ("realtime", 0)

	@pytest.mark.parametrize(
		"raw",
		["nope", "best-effort:99", "realtime:-1", "best-effort:x"],
	)
	def test_invalid(self, raw: str):
		with pytest.raises(ValueError):
			parse_ionice_spec(raw)


class TestStartOptionsValidation:
	def test_valid_defaults(self):
		options = StartOptions(cmd="sleep 10")
		options.validate()

	def test_invalid_startup_timeout(self):
		options = StartOptions(cmd="sleep 10", startup_timeout_seconds=0)
		with pytest.raises(ValueError, match="startup-timeout"):
			options.validate()

	def test_invalid_instances(self):
		options = StartOptions(cmd="sleep 10", instances=0)
		with pytest.raises(ValueError, match="instances"):
			options.validate()

	def test_invalid_nice(self):
		options = StartOptions(cmd="sleep 10", nice=99)
		with pytest.raises(ValueError, match="nice"):
			options.validate()

	def test_invalid_ionice(self):
		options = StartOptions(cmd="sleep 10", ionice="nope")
		with pytest.raises(ValueError, match="ionice"):
			options.validate()

	def test_conflicting_health_checks(self):
		options = StartOptions(cmd="sleep 10", health_http="http://x/", health_tcp="127.0.0.1:9000")
		with pytest.raises(ValueError, match="only one"):
			options.validate()

	def test_invalid_health_interval(self):
		options = StartOptions(cmd="sleep 10", health_http="http://x/", health_interval=0)
		with pytest.raises(ValueError, match="health-interval"):
			options.validate()

	def test_invalid_health_timeout(self):
		options = StartOptions(cmd="sleep 10", health_tcp="127.0.0.1:9000", health_timeout=0)
		with pytest.raises(ValueError, match="health-timeout"):
			options.validate()

	def test_invalid_health_failures(self):
		options = StartOptions(cmd="sleep 10", health_tcp="127.0.0.1:9000", health_failures=0)
		with pytest.raises(ValueError, match="health-failures"):
			options.validate()


class TestStartOptionsHealthCheck:
	def test_no_health_check(self):
		options = StartOptions(cmd="sleep 10")
		assert options.health_check is None

	def test_http_health_check(self):
		options = StartOptions(
			cmd="sleep 10",
			health_http="http://127.0.0.1:8000/health",
			health_interval=10.0,
			health_timeout=2.0,
			health_failures=2,
		)
		assert options.health_check == HealthCheckConfig(
			kind="http",
			target="http://127.0.0.1:8000/health",
			interval_seconds=10.0,
			timeout_seconds=2.0,
			failure_threshold=2,
		)

	def test_tcp_health_check(self):
		options = StartOptions(cmd="sleep 10", health_tcp="127.0.0.1:9000")
		assert options.health_check is not None
		assert options.health_check.kind == "tcp"

	def test_ionice_spec_resolution(self):
		assert StartOptions(cmd="x").ionice_spec() == (None, None)
		assert StartOptions(cmd="x", ionice="idle").ionice_spec() == ("idle", None)
		assert StartOptions(cmd="x", ionice="best-effort:2").ionice_spec() == ("best_effort", 2)
