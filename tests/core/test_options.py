"""Tests for StartOptions validation and ionice parsing"""

import pytest

from sentinel_core.models import AutoscaleConfig, DockerConfig
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
		[
			"nope",
			"best-effort:99",
			"realtime:-1",
			"best-effort:x",
			"best-effort:8",
			"realtime:8",
			"idle:0",
			"best effort",
		],
	)
	def test_invalid(self, raw: str):
		with pytest.raises(ValueError, match="ionice"):
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

	def test_autoscale_requires_a_scale_range(self):
		options = StartOptions(cmd="sleep 10", autoscale=["cpu:80:40"])
		with pytest.raises(ValueError, match="requires --scale"):
			options.validate()

	def test_autoscale_rejects_a_fixed_scale(self):
		options = StartOptions(cmd="sleep 10", scale="2", autoscale=["cpu:80:40"])
		with pytest.raises(ValueError, match="MIN-MAX"):
			options.validate()

	def test_invalid_autoscale_spec(self):
		options = StartOptions(cmd="sleep 10", scale="2-4", autoscale=["cpu:40"])
		with pytest.raises(ValueError, match="autoscale"):
			options.validate()

	def test_valid_autoscale_with_a_range(self):
		options = StartOptions(cmd="sleep 10", scale="2-4", autoscale=["cpu:80:40", "mem:800:300"])
		options.validate()
		assert options.autoscale_config == AutoscaleConfig(
			cpu_high=80.0, cpu_low=40.0, mem_high_mb=800.0, mem_low_mb=300.0
		)


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


class TestDockerOptions:
	def test_docker_image_alone_is_valid(self):
		options = StartOptions(cmd="sleep 30", docker_image="alpine")

		options.validate()

	def test_blank_docker_image_is_rejected(self):
		options = StartOptions(cmd="sleep 30", docker_image="   ")

		with pytest.raises(ValueError, match="--docker-image requires an image name"):
			options.validate()

	def test_docker_ports_and_volumes_require_an_image(self):
		for options in (
			StartOptions(cmd="sleep 30", docker_ports=["8080:80"]),
			StartOptions(cmd="sleep 30", docker_volumes=["data:/data"]),
		):
			with pytest.raises(ValueError, match="require --docker-image"):
				options.validate()

	def test_docker_image_rejects_host_only_flags(self):
		for options in (
			StartOptions(cmd="sleep 30", docker_image="alpine", user="root"),
			StartOptions(cmd="sleep 30", docker_image="alpine", nice=5),
			StartOptions(cmd="sleep 30", docker_image="alpine", ionice="idle"),
			StartOptions(cmd="sleep 30", docker_image="alpine", cwd="/tmp"),
		):
			with pytest.raises(ValueError, match="cannot be combined"):
				options.validate()

	def test_docker_engine_must_be_known(self):
		options = StartOptions(cmd="sleep 30", docker_image="alpine", docker_engine="containerd")

		with pytest.raises(ValueError, match="--docker-engine must be docker or podman"):
			options.validate()

	def test_docker_config_carries_the_raw_engine_choice(self):
		options = StartOptions(
			cmd="sleep 30",
			docker_image=" alpine:latest ",
			docker_ports=["8080:80"],
			docker_volumes=["data:/data"],
			docker_engine="podman",
		)
		options.validate()

		assert options.docker_config == DockerConfig(
			image="alpine:latest", ports=["8080:80"], volumes=["data:/data"], engine="podman"
		)

	def test_docker_config_is_none_without_an_image(self):
		assert StartOptions(cmd="sleep 30").docker_config is None
