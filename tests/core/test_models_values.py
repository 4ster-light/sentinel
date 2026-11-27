"""Round-trip tests for the state models"""

from sentinel_core import models
from sentinel_core.models import (
	AutoscaleConfig,
	DockerConfig,
	GroupInfo,
	HealthCheckConfig,
	PortInfo,
	ProcessInfo,
	RemoteInfo,
)


class TestHealthCheckConfig:
	def test_round_trips(self) -> None:
		config = HealthCheckConfig(
			kind="http", target="http://x/", interval_seconds=10.0, timeout_seconds=2.0, failure_threshold=5
		)

		assert HealthCheckConfig.from_dict(config.to_dict()) == config

	def test_defaults_fill_missing_keys(self) -> None:
		config = HealthCheckConfig.from_dict({"kind": "tcp", "target": "host:1"})

		assert config == HealthCheckConfig(kind="tcp", target="host:1")


class TestAutoscaleConfig:
	def test_round_trips(self) -> None:
		config = AutoscaleConfig(
			cpu_high=80.0,
			cpu_low=40.0,
			mem_high_mb=800.0,
			mem_low_mb=300.0,
			cooldown_seconds=15.0,
			step=2,
			metric_path="/run/x",
			metric_high=9.0,
			metric_low=3.0,
		)

		assert AutoscaleConfig.from_dict(config.to_dict()) == config

	def test_defaults_fill_missing_keys(self) -> None:
		assert AutoscaleConfig.from_dict({}) == AutoscaleConfig()

	def test_describes_every_part(self) -> None:
		config = AutoscaleConfig(
			cpu_high=80.0,
			cpu_low=40.0,
			mem_high_mb=800.0,
			mem_low_mb=300.0,
			metric_path="/run/x",
			metric_high=9.0,
			metric_low=3.0,
			cooldown_seconds=15.0,
			step=2,
		)

		assert config.describe() == "cpu:80:40 mem:800:300 metric:/run/x:9:3 cooldown:15 step:2"

	def test_describes_nothing_by_default(self) -> None:
		assert AutoscaleConfig().describe() == ""

	def test_describes_cpu_only(self) -> None:
		assert AutoscaleConfig(cpu_high=80.0, cpu_low=40.0).describe() == "cpu:80:40"

	def test_formats_thresholds(self) -> None:
		assert models._format_threshold(80.0) == "80"
		assert models._format_threshold(0.5) == "0.5"


class TestDockerConfig:
	def test_round_trips(self) -> None:
		config = DockerConfig(image="nginx", ports=["80:80"], volumes=["data:/data"], engine="podman")

		assert DockerConfig.from_dict(config.to_dict()) == config

	def test_missing_lists_become_empty(self) -> None:
		assert DockerConfig.from_dict({"image": "x"}) == DockerConfig(image="x")


class TestProcessInfo:
	def test_round_trips_every_field(self) -> None:
		info = ProcessInfo(
			id=1,
			pid=2,
			name="api",
			cmd="true",
			cwd="/",
			restart=True,
			started_at="2026-01-01T00:00:00",
			stdout_log="out.log",
			stderr_log="err.log",
			user="alice",
			env={"A": "1"},
			group="staff",
			depends_on=["db"],
			cluster="web",
			cluster_index=1,
			cluster_min=2,
			cluster_max=4,
			autoscale=AutoscaleConfig(cpu_high=1.0, cpu_low=0.5),
			env_file=".env",
			docker=DockerConfig(image="nginx"),
			health_check=HealthCheckConfig(kind="tcp", target="host:1"),
			health_failures=2,
			health_last_checked_at="2026-01-01T00:00:01",
			startup_timeout_seconds=30.0,
			nice=5,
			ionice_ioclass="best_effort",
			ionice_value=2,
			stopped=True,
			create_time=3.0,
			base_env={"B": "2"},
		)

		assert ProcessInfo.from_dict(info.to_dict()) == info

	def test_defaults_fill_missing_keys(self) -> None:
		data = {
			"id": 1,
			"pid": 2,
			"name": "api",
			"cmd": "true",
			"cwd": "/",
			"restart": False,
			"started_at": "",
			"stdout_log": "",
			"stderr_log": "",
		}

		info = ProcessInfo.from_dict(data)

		assert info.env == {}
		assert info.depends_on == []
		assert info.autoscale is None
		assert info.docker is None
		assert info.health_check is None
		assert info.health_failures == 0
		assert info.stopped is False
		assert info.create_time is None
		assert info.base_env is None


class TestOtherModels:
	def test_group_round_trips(self) -> None:
		group = GroupInfo(name="web", created_at="t", env={"A": "1"}, env_file=".env")

		assert GroupInfo.from_dict(group.to_dict()) == group

	def test_port_round_trips(self) -> None:
		port = PortInfo(port=4000, name="web", allocated_at="t")

		assert PortInfo.from_dict(port.to_dict()) == port

	def test_remote_round_trips(self) -> None:
		remote = RemoteInfo(host="host", user="alice", port=22, created_at="t", batch_mode=False)

		assert RemoteInfo.from_dict(remote.to_dict()) == remote

	def test_remote_defaults_fill_missing_keys(self) -> None:
		assert RemoteInfo.from_dict({"host": "host"}) == RemoteInfo(host="host")


def test_autoscale_describe_ignores_half_configured_pairs() -> None:
	assert AutoscaleConfig(cpu_high=80.0).describe() == ""
	assert AutoscaleConfig(mem_low_mb=300.0).describe() == ""
	assert AutoscaleConfig(metric_path="/run/x", metric_low=3.0).describe() == ""
