"""Tests for CPU/memory-driven cluster autoscaling"""

import os
import time
from pathlib import Path

import pytest

from sentinel_core.autoscale import DEFAULT_COOLDOWN_SECONDS, apply_autoscaling, autoscale_decision
from sentinel_core.cluster import ScaleSpec, cluster_members, instance_name
from sentinel_core.models import AutoscaleConfig, ProcessInfo, ProcessStatus
from sentinel_core.options import parse_autoscale_specs
from sentinel_core.process import batch_stop_processes, restart_process, start_process
from sentinel_core.restart_monitor import RestartMonitor
from sentinel_core.state import State


@pytest.fixture(autouse=True)
def stop_cluster_processes(state: State):
	yield
	batch_stop_processes(state, state.list_processes(), force=True)


class TestParseAutoscaleSpecs:
	def test_parses_cpu_and_mem_thresholds(self) -> None:
		config = parse_autoscale_specs(["cpu:80:40", "mem:800:300"])

		assert config == AutoscaleConfig(cpu_high=80.0, cpu_low=40.0, mem_high_mb=800.0, mem_low_mb=300.0)

	def test_empty_specs_produce_no_policy(self) -> None:
		assert parse_autoscale_specs([]) == AutoscaleConfig()

	def test_parses_a_custom_metric_spec(self) -> None:
		config = parse_autoscale_specs(["metric:/var/run/app/depth:80:40"])

		assert config.metric_path == "/var/run/app/depth"
		assert (config.metric_high, config.metric_low) == (80.0, 40.0)
		assert config.describe() == "metric:/var/run/app/depth:80:40"

	def test_describe_renders_the_policy(self) -> None:
		config = parse_autoscale_specs(["cpu:80:40", "mem:800:300"])

		assert config.describe() == "cpu:80:40 mem:800:300"

	@pytest.mark.parametrize(
		"specs",
		[
			["cpu"],
			["cpu:80"],
			["cpu:80:40:2"],
			["cpu:80:40", "cpu:90:50"],
			["mem:800:300", "mem:900:400"],
			["disk:80:40"],
			["metric"],
			["metric:80:40"],
			["metric:/depth:40:80"],
			["metric:/depth:80:40", "metric:/other:90:50"],
			["cpu:40:80"],
			["cpu:80:80"],
			["cpu:80:0"],
			["cpu:eight:forty"],
			["cpu:inf:40"],
			["cpu:80:nan"],
		],
	)
	def test_invalid_specs_are_rejected(self, specs: list[str]) -> None:
		with pytest.raises(ValueError, match="autoscale"):
			parse_autoscale_specs(specs)


class TestAutoscaleDecision:
	def test_grows_when_cpu_is_hot(self) -> None:
		config = AutoscaleConfig(cpu_high=80, cpu_low=40)

		assert autoscale_decision(config, 90, 10, ScaleSpec(2, 4), 2) == 3

	def test_grows_when_memory_is_hot(self) -> None:
		config = AutoscaleConfig(mem_high_mb=800, mem_low_mb=300)

		assert autoscale_decision(config, 10, 900, ScaleSpec(2, 4), 2) == 3

	def test_no_growth_beyond_the_maximum(self) -> None:
		config = AutoscaleConfig(cpu_high=80, cpu_low=40)

		assert autoscale_decision(config, 90, 10, ScaleSpec(2, 4), 4) is None

	def test_shrinks_when_every_configured_metric_is_cool(self) -> None:
		config = AutoscaleConfig(cpu_high=80, cpu_low=40, mem_high_mb=800, mem_low_mb=300)

		assert autoscale_decision(config, 10, 50, ScaleSpec(2, 4), 4) == 3

	def test_hot_memory_blocks_shrinking(self) -> None:
		config = AutoscaleConfig(cpu_high=80, cpu_low=40, mem_high_mb=800, mem_low_mb=300)

		assert autoscale_decision(config, 10, 900, ScaleSpec(2, 4), 4) is None

	def test_no_shrink_below_the_minimum(self) -> None:
		config = AutoscaleConfig(cpu_high=80, cpu_low=40)

		assert autoscale_decision(config, 10, 0, ScaleSpec(2, 4), 2) is None

	def test_unconfigured_metrics_do_not_block_shrinking(self) -> None:
		config = AutoscaleConfig(cpu_high=80, cpu_low=40)

		assert autoscale_decision(config, 10, 900, ScaleSpec(2, 4), 3) == 2

	def test_step_grows_by_the_policy_step(self) -> None:
		config = AutoscaleConfig(cpu_high=80, cpu_low=40, step=2)

		assert autoscale_decision(config, 90, 10, ScaleSpec(2, 6), 2, avg_metric=None) == 4

	def test_step_shrinks_by_the_policy_step(self) -> None:
		config = AutoscaleConfig(cpu_high=80, cpu_low=40, step=2)

		assert autoscale_decision(config, 10, 0, ScaleSpec(2, 6), 5, avg_metric=None) == 3

	def test_step_growth_clamps_to_the_maximum(self) -> None:
		config = AutoscaleConfig(cpu_high=80, cpu_low=40, step=2)

		assert autoscale_decision(config, 90, 10, ScaleSpec(2, 6), 5, avg_metric=None) == 6

	def test_step_shrink_clamps_to_the_minimum(self) -> None:
		config = AutoscaleConfig(cpu_high=80, cpu_low=40, step=2)

		assert autoscale_decision(config, 10, 0, ScaleSpec(2, 6), 3, avg_metric=None) == 2

	def test_a_hot_metric_grows_the_cluster(self) -> None:
		config = AutoscaleConfig(metric_high=80, metric_low=40)

		assert autoscale_decision(config, 10, 0, ScaleSpec(2, 6), 2, avg_metric=90) == 3

	def test_a_cool_metric_allows_shrinking(self) -> None:
		config = AutoscaleConfig(cpu_high=80, cpu_low=40, metric_high=80, metric_low=40)

		assert autoscale_decision(config, 10, 0, ScaleSpec(2, 6), 4, avg_metric=10) == 3

	def test_a_metric_between_thresholds_blocks_shrinking(self) -> None:
		config = AutoscaleConfig(cpu_high=80, cpu_low=40, metric_high=80, metric_low=40)

		assert autoscale_decision(config, 10, 0, ScaleSpec(2, 6), 4, avg_metric=60) is None


class TestApplyAutoscaling:
	@staticmethod
	def _start_cluster(state: State, count: int, config: AutoscaleConfig | None) -> None:
		for index in range(1, count + 1):
			start_process(
				state,
				"sleep 30",
				name=instance_name("web", index),
				cluster="web",
				cluster_index=index,
				cluster_min=1,
				cluster_max=4,
				autoscale=config,
			)

	def test_idle_cpu_shrinks_the_cluster(self, state: State) -> None:
		self._start_cluster(state, 2, AutoscaleConfig(cpu_high=80, cpu_low=40))

		adjustments = apply_autoscaling(State(), {})

		assert adjustments == [("web", 2, 1)]
		assert [info.name for info in cluster_members(State(), "web")] == ["web-1"]

	def test_hot_cpu_grows_the_cluster(self, state: State, monkeypatch: pytest.MonkeyPatch) -> None:
		self._start_cluster(state, 2, AutoscaleConfig(cpu_high=80, cpu_low=40))

		def fake_status(info: ProcessInfo) -> ProcessStatus:
			return ProcessStatus(running=True, status="running", cpu_percent=90, memory_mb=10)

		monkeypatch.setattr("sentinel_core.autoscale.get_process_status", fake_status)
		adjustments = apply_autoscaling(State(), {})

		assert adjustments == [("web", 2, 3)]
		assert [info.name for info in cluster_members(State(), "web")] == ["web-1", "web-2", "web-3"]

	def test_grown_instances_inherit_the_policy(self, state: State, monkeypatch: pytest.MonkeyPatch) -> None:
		config = AutoscaleConfig(cpu_high=80, cpu_low=40)
		self._start_cluster(state, 2, config)

		def fake_status(info: ProcessInfo) -> ProcessStatus:
			return ProcessStatus(running=True, status="running", cpu_percent=90, memory_mb=10)

		monkeypatch.setattr("sentinel_core.autoscale.get_process_status", fake_status)
		apply_autoscaling(State(), {})

		grown = State().find_process_by_name("web-3")

		assert grown is not None
		assert grown.autoscale == config

	def test_cooldown_blocks_recent_adjustments(self, state: State) -> None:
		self._start_cluster(state, 2, AutoscaleConfig(cpu_high=80, cpu_low=40))
		last_adjusted = {"web": time.monotonic()}

		adjustments = apply_autoscaling(State(), last_adjusted)

		assert adjustments == []
		assert len(cluster_members(State(), "web")) == 2

	def test_a_short_policy_cooldown_allows_recent_adjustments(self, state: State) -> None:
		self._start_cluster(state, 2, AutoscaleConfig(cpu_high=80, cpu_low=40, cooldown_seconds=15))
		last_adjusted = {"web": time.monotonic() - 20}

		adjustments = apply_autoscaling(State(), last_adjusted)

		assert adjustments == [("web", 2, 1)]

	def test_the_default_cooldown_still_blocks(self, state: State) -> None:
		self._start_cluster(state, 2, AutoscaleConfig(cpu_high=80, cpu_low=40))
		last_adjusted = {"web": time.monotonic() - DEFAULT_COOLDOWN_SECONDS + 5}

		adjustments = apply_autoscaling(State(), last_adjusted)

		assert adjustments == []
		assert len(cluster_members(State(), "web")) == 2

	def test_a_hot_metric_file_grows_the_cluster(self, state: State, tmp_path: Path) -> None:
		metric_file = tmp_path / "depth"
		metric_file.write_text("90\n")
		self._start_cluster(state, 2, AutoscaleConfig(metric_path=str(metric_file), metric_high=80, metric_low=40))

		adjustments = apply_autoscaling(State(), {})

		assert adjustments == [("web", 2, 3)]

	def test_a_cool_metric_file_shrinks_the_cluster(self, state: State, tmp_path: Path) -> None:
		metric_file = tmp_path / "depth"
		metric_file.write_text("10\n")
		self._start_cluster(state, 2, AutoscaleConfig(metric_path=str(metric_file), metric_high=80, metric_low=40))

		adjustments = apply_autoscaling(State(), {})

		assert adjustments == [("web", 2, 1)]

	def test_a_missing_metric_file_causes_no_action(self, state: State, tmp_path: Path) -> None:
		self._start_cluster(
			state,
			2,
			AutoscaleConfig(
				cpu_high=80, cpu_low=40, metric_path=str(tmp_path / "absent"), metric_high=80, metric_low=40
			),
		)

		adjustments = apply_autoscaling(State(), {})

		assert adjustments == []
		assert len(cluster_members(State(), "web")) == 2

	def test_an_unreadable_metric_file_causes_no_action(self, state: State, tmp_path: Path) -> None:
		self._start_cluster(
			state,
			2,
			AutoscaleConfig(cpu_high=80, cpu_low=40, metric_path=str(tmp_path), metric_high=80, metric_low=40),
		)

		adjustments = apply_autoscaling(State(), {})

		assert adjustments == []
		assert len(cluster_members(State(), "web")) == 2

	def test_a_stale_metric_file_causes_no_action(self, state: State, tmp_path: Path) -> None:
		metric_file = tmp_path / "depth"
		metric_file.write_text("90\n")
		old = time.time() - 3600
		os.utime(metric_file, (old, old))
		self._start_cluster(state, 2, AutoscaleConfig(metric_path=str(metric_file), metric_high=80, metric_low=40))

		adjustments = apply_autoscaling(State(), {})

		assert adjustments == []
		assert len(cluster_members(State(), "web")) == 2

	def test_an_unparsable_metric_file_causes_no_action(self, state: State, tmp_path: Path) -> None:
		metric_file = tmp_path / "depth"
		metric_file.write_text("not-a-number")
		self._start_cluster(
			state,
			2,
			AutoscaleConfig(cpu_high=80, cpu_low=40, metric_path=str(metric_file), metric_high=80, metric_low=40),
		)

		adjustments = apply_autoscaling(State(), {})

		assert adjustments == []
		assert len(cluster_members(State(), "web")) == 2

	def test_stale_cooldown_allows_one_adjustment(self, state: State) -> None:
		self._start_cluster(state, 2, AutoscaleConfig(cpu_high=80, cpu_low=40))
		last_adjusted = {"web": time.monotonic() - DEFAULT_COOLDOWN_SECONDS - 1}

		adjustments = apply_autoscaling(State(), last_adjusted)

		assert adjustments == [("web", 2, 1)]
		assert last_adjusted["web"] > time.monotonic() - 1

	def test_on_scale_receives_each_adjustment(self, state: State) -> None:
		self._start_cluster(state, 2, AutoscaleConfig(cpu_high=80, cpu_low=40))
		events: list[tuple[str, int, int]] = []

		apply_autoscaling(
			State(), {}, on_scale=lambda cluster, previous, desired: events.append((cluster, previous, desired))
		)

		assert events == [("web", 2, 1)]

	def test_clusters_without_a_policy_are_untouched(self, state: State) -> None:
		self._start_cluster(state, 2, None)

		adjustments = apply_autoscaling(State(), {})

		assert adjustments == []
		assert len(cluster_members(State(), "web")) == 2

	def test_restart_preserves_the_policy(self, state: State) -> None:
		self._start_cluster(state, 1, AutoscaleConfig(cpu_high=80, cpu_low=40))

		restarted = restart_process(State(), "web-1")

		assert restarted.autoscale == AutoscaleConfig(cpu_high=80, cpu_low=40)

	def test_policy_survives_a_state_roundtrip(self, state: State) -> None:
		config = AutoscaleConfig(cpu_high=80, cpu_low=40, mem_high_mb=800, mem_low_mb=300)
		self._start_cluster(state, 1, config)

		reloaded = State().find_process_by_name("web-1")

		assert reloaded is not None
		assert reloaded.autoscale == config


class TestMonitorScaleCallback:
	def test_monitor_scale_callback_plumbing(self) -> None:
		monitor = RestartMonitor(check_interval=0.1)
		events: list[tuple[str, int, int]] = []
		monitor.set_scale_callback(lambda cluster, previous, desired: events.append((cluster, previous, desired)))

		monitor._on_scale("web", 2, 3)

		assert events == [("web", 2, 3)]
