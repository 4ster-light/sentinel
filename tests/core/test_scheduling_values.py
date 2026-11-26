"""Value tests for dependency ordering, scale ranges and the autoscale decision"""

import os
import time
from pathlib import Path

import pytest

from sentinel_core.autoscale import DEFAULT_METRIC_STALE_SECONDS, autoscale_decision, read_metric_value
from sentinel_core.cluster import ScaleSpec, instance_name
from sentinel_core.dependencies import DependencyError, _find_cycle, start_order, stop_order
from sentinel_core.models import AutoscaleConfig, ProcessInfo


def process(name: str, depends_on: tuple[str, ...] = ()) -> ProcessInfo:
	return ProcessInfo(
		id=0,
		pid=0,
		name=name,
		cmd="true",
		cwd="/",
		restart=False,
		started_at="",
		stdout_log="",
		stderr_log="",
		depends_on=list(depends_on),
	)


class TestStartOrder:
	def test_dependency_precedes_dependent(self) -> None:
		web = process("web", ("app",))
		app = process("app", ("db",))
		db = process("db")

		assert [p.name for p in start_order([web, app, db])] == ["db", "app", "web"]

	def test_diamond_keeps_input_order_between_peers(self) -> None:
		top = process("top", ("left", "right"))
		left = process("left", ("base",))
		right = process("right", ("base",))
		base = process("base")

		assert [p.name for p in start_order([top, left, right, base])] == ["base", "left", "right", "top"]

	def test_independent_processes_keep_input_order(self) -> None:
		assert [p.name for p in start_order([process("c"), process("a"), process("b")])] == ["c", "a", "b"]

	def test_unknown_dependency_is_rejected(self) -> None:
		with pytest.raises(DependencyError) as excinfo:
			start_order([process("web", ("db",))])

		assert str(excinfo.value) == "Process 'web' depends on 'db', which is neither in this batch nor running"

	def test_available_dependency_is_accepted(self) -> None:
		assert [p.name for p in start_order([process("web", ("db",))], available={"db"})] == ["web"]

	def test_non_strict_ignores_an_unknown_dependency(self) -> None:
		assert [p.name for p in start_order([process("web", ("db",))], strict=False)] == ["web"]

	def test_duplicate_name_is_rejected(self) -> None:
		with pytest.raises(DependencyError) as excinfo:
			start_order([process("web"), process("web")])

		assert str(excinfo.value) == "Duplicate process name 'web' in the dependency graph"

	def test_self_dependency_is_rejected(self) -> None:
		with pytest.raises(DependencyError) as excinfo:
			start_order([process("web", ("web",))])

		assert str(excinfo.value) == "Process 'web' cannot depend on itself"

	def test_cycle_reports_one_path(self) -> None:
		with pytest.raises(DependencyError) as excinfo:
			start_order([process("a", ("b",)), process("b", ("a",))])

		assert str(excinfo.value) == "Dependency cycle: a -> b -> a"

	def test_duplicate_dependency_edges_count_once(self) -> None:
		web = process("web", ("db", "db"))
		db = process("db")

		assert [p.name for p in start_order([web, db])] == ["db", "web"]


class TestStopOrder:
	def test_reverses_the_start_order(self) -> None:
		web = process("web", ("db",))
		db = process("db")

		assert [p.name for p in stop_order([db, web])] == ["web", "db"]

	def test_cycle_falls_back_to_the_input_order(self) -> None:
		a = process("a", ("b",))
		b = process("b", ("a",))

		assert [p.name for p in stop_order([a, b])] == ["a", "b"]


class TestFindCycle:
	def test_returns_the_sorted_nodes_without_a_cycle(self) -> None:
		assert _find_cycle({"b", "a"}, {"a": [], "b": []}) == ["a", "b"]


class TestScaleSpec:
	@pytest.mark.parametrize(
		("raw", "expected"),
		[("2", (2, 2)), ("2-4", (2, 4)), (" 3 ", (3, 3)), ("1-64", (1, 64))],
	)
	def test_parses_a_range(self, raw: str, expected: tuple[int, int]) -> None:
		spec = ScaleSpec.parse(raw)

		assert (spec.min_instances, spec.max_instances) == expected

	@pytest.mark.parametrize("raw", ["0", "4-2", "1-65", "x", "2-", "-3", ""])
	def test_rejects_an_invalid_range(self, raw: str) -> None:
		with pytest.raises(ValueError, match="scale"):
			ScaleSpec.parse(raw)

	@pytest.mark.parametrize(("count", "expected"), [(1, False), (2, True), (3, True), (4, True), (5, False)])
	def test_allows_the_inclusive_range(self, count: int, expected: bool) -> None:
		assert ScaleSpec(2, 4).allows(count) is expected

	def test_describes_a_fixed_size_and_a_range(self) -> None:
		assert ScaleSpec(2, 2).describe() == "2"
		assert ScaleSpec(2, 4).describe() == "2-4"

	def test_instance_name(self) -> None:
		assert instance_name("web", 2) == "web-2"


def policy_config(
	*,
	cpu_high: float | None = None,
	cpu_low: float | None = None,
	mem_high_mb: float | None = None,
	mem_low_mb: float | None = None,
	metric_path: str | None = None,
	metric_high: float | None = None,
	metric_low: float | None = None,
	step: int = 1,
) -> AutoscaleConfig:
	return AutoscaleConfig(
		cpu_high=cpu_high,
		cpu_low=cpu_low,
		mem_high_mb=mem_high_mb,
		mem_low_mb=mem_low_mb,
		metric_path=metric_path,
		metric_high=metric_high,
		metric_low=metric_low,
		step=step,
	)


class TestAutoscaleDecision:
	def test_hot_cpu_grows_by_one_step(self) -> None:
		policy = policy_config(cpu_high=80.0, cpu_low=40.0)

		assert autoscale_decision(policy, 90.0, 10.0, ScaleSpec(2, 4), 2) == 3

	def test_hot_memory_grows(self) -> None:
		policy = policy_config(mem_high_mb=800.0, mem_low_mb=300.0)

		assert autoscale_decision(policy, 10.0, 900.0, ScaleSpec(2, 4), 2) == 3

	def test_hot_metric_grows(self) -> None:
		policy = policy_config(metric_path="/run/depth", metric_high=10.0, metric_low=4.0)

		assert autoscale_decision(policy, 10.0, 10.0, ScaleSpec(2, 4), 2, avg_metric=11.0) == 3

	def test_growth_is_clamped_to_the_maximum(self) -> None:
		policy = policy_config(cpu_high=80.0, cpu_low=40.0, step=5)

		assert autoscale_decision(policy, 90.0, 10.0, ScaleSpec(2, 4), 3) == 4

	def test_at_the_maximum_stays(self) -> None:
		policy = policy_config(cpu_high=80.0, cpu_low=40.0)

		assert autoscale_decision(policy, 90.0, 10.0, ScaleSpec(2, 4), 4) is None

	def test_cool_metrics_shrink(self) -> None:
		policy = policy_config(cpu_high=80.0, cpu_low=40.0, mem_high_mb=800.0, mem_low_mb=300.0)

		assert autoscale_decision(policy, 10.0, 100.0, ScaleSpec(2, 4), 4) == 3

	def test_shrink_is_clamped_to_the_minimum(self) -> None:
		policy = policy_config(cpu_high=80.0, cpu_low=40.0, step=5)

		assert autoscale_decision(policy, 10.0, 10.0, ScaleSpec(2, 4), 3) == 2

	def test_at_the_minimum_stays(self) -> None:
		policy = policy_config(cpu_high=80.0, cpu_low=40.0)

		assert autoscale_decision(policy, 10.0, 10.0, ScaleSpec(2, 4), 2) is None

	def test_a_warm_metric_blocks_shrink(self) -> None:
		policy = policy_config(cpu_high=80.0, cpu_low=40.0)

		assert autoscale_decision(policy, 50.0, 10.0, ScaleSpec(2, 4), 4) is None

	def test_a_missing_metric_value_blocks_shrink(self) -> None:
		policy = policy_config(metric_path="/run/depth", metric_high=10.0, metric_low=4.0)

		assert autoscale_decision(policy, 10.0, 10.0, ScaleSpec(2, 4), 4, avg_metric=None) is None

	def test_no_thresholds_shrink_to_the_minimum(self) -> None:
		assert autoscale_decision(policy_config(), 0.0, 0.0, ScaleSpec(2, 4), 4) == 3


class TestReadMetricValue:
	def test_returns_none_without_a_path(self) -> None:
		assert read_metric_value(policy_config()) is None

	def test_reads_a_fresh_value(self, tmp_path: Path) -> None:
		metric = tmp_path / "depth"
		metric.write_text("12.5\n")

		assert read_metric_value(policy_config(metric_path=str(metric))) == 12.5

	def test_returns_none_for_a_stale_file(self, tmp_path: Path) -> None:
		metric = tmp_path / "depth"
		metric.write_text("12.5\n")
		old = time.time() - DEFAULT_METRIC_STALE_SECONDS - 10
		os.utime(metric, (old, old))

		assert read_metric_value(policy_config(metric_path=str(metric))) is None

	def test_returns_none_for_a_missing_file(self, tmp_path: Path) -> None:
		assert read_metric_value(policy_config(metric_path=str(tmp_path / "absent"))) is None

	def test_returns_none_for_an_unparsable_file(self, tmp_path: Path) -> None:
		metric = tmp_path / "depth"
		metric.write_text("not a number\n")

		assert read_metric_value(policy_config(metric_path=str(metric))) is None
