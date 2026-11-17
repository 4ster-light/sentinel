"""Tests for cluster scale ranges and resizing"""

import pytest

from sentinel_core.cluster import (
	MAX_INSTANCES,
	ScaleSpec,
	cluster_members,
	cluster_spec,
	instance_name,
	scale_cluster,
)
from sentinel_core.models import ProcessInfo
from sentinel_core.process import batch_stop_processes, restart_process, start_process
from sentinel_core.state import State


@pytest.fixture(autouse=True)
def stop_cluster_processes(state: State):
	yield
	batch_stop_processes(state, state.list_processes(), force=True)


def start_instance(state: State, name: str, index: int, minimum: int, maximum: int, **kwargs) -> None:
	start_process(
		state,
		"sleep 30",
		name=instance_name(name, index),
		cluster=name,
		cluster_index=index,
		cluster_min=minimum,
		cluster_max=maximum,
		**kwargs,
	)


class TestScaleSpec:
	@pytest.mark.parametrize(
		("raw", "expected"),
		[
			("3", (3, 3)),
			("2-4", (2, 4)),
			(" 1 - 2 ", (1, 2)),
			("1-1", (1, 1)),
			(str(MAX_INSTANCES), (MAX_INSTANCES, MAX_INSTANCES)),
		],
	)
	def test_parse_valid(self, raw: str, expected: tuple[int, int]):
		spec = ScaleSpec.parse(raw)

		assert (spec.min_instances, spec.max_instances) == expected

	@pytest.mark.parametrize(
		"raw",
		["", " ", "0", "0-2", "4-2", "abc", "1-2-3", "-2", "1-", f"1-{MAX_INSTANCES + 1}"],
	)
	def test_parse_invalid(self, raw: str):
		with pytest.raises(ValueError, match=r"scale|invalid"):
			ScaleSpec.parse(raw)

	def test_allows_only_its_range(self):
		spec = ScaleSpec(2, 4)

		assert spec.allows(2)
		assert spec.allows(4)
		assert not spec.allows(1)
		assert not spec.allows(5)

	def test_describe(self):
		assert ScaleSpec(2, 2).describe() == "2"
		assert ScaleSpec(2, 4).describe() == "2-4"

	def test_instance_name(self):
		assert instance_name("web", 3) == "web-3"


class TestScaleCluster:
	def test_grow_adds_missing_indices(self, state: State):
		start_instance(state, "web", 1, 1, 4)

		result = scale_cluster(State(), "web", 3)

		assert [info.name for info in result.started] == ["web-2", "web-3"]
		assert [info.cluster_index for info in cluster_members(State(), "web")] == [1, 2, 3]

	def test_shrink_stops_highest_indices_and_drops_them(self, state: State):
		for index in range(1, 4):
			start_instance(state, "web", index, 1, 4)

		result = scale_cluster(State(), "web", 1)

		assert [info.name for info in result.stopped] == ["web-2", "web-3"]
		assert [info.name for info in cluster_members(State(), "web")] == ["web-1"]
		assert State().find_process_by_name("web-2") is None

	def test_rejects_counts_outside_the_range(self, state: State):
		start_instance(state, "web", 1, 2, 4)

		with pytest.raises(ValueError, match="allows 2-4 instances, not 5"):
			scale_cluster(State(), "web", 5)
		with pytest.raises(ValueError, match="allows 2-4 instances, not 1"):
			scale_cluster(State(), "web", 1)

	def test_unknown_cluster_is_rejected(self, state: State):
		with pytest.raises(ValueError, match="Unknown cluster 'web'"):
			scale_cluster(State(), "web", 2)

	def test_restart_preserves_cluster_metadata(self, state: State):
		start_instance(state, "web", 1, 2, 4)

		restarted = restart_process(State(), "web-1")

		assert restarted.cluster == "web"
		assert restarted.cluster_index == 1
		assert restarted.cluster_min == 2
		assert restarted.cluster_max == 4

	def test_grown_instances_inherit_configuration_and_dependencies(self, state: State):
		start_instance(state, "api", 1, 1, 3, depends_on=["db"], restart=True)

		result = scale_cluster(State(), "api", 2)

		assert len(result.started) == 1
		assert result.started[0].depends_on == ["db"]
		assert result.started[0].restart is True

	def test_cluster_spec_falls_back_to_member_count(self):
		members = [
			ProcessInfo(
				id=1,
				pid=0,
				name="web-1",
				cmd="true",
				cwd="/",
				restart=False,
				started_at="",
				stdout_log="",
				stderr_log="",
				cluster="web",
				cluster_index=1,
			),
			ProcessInfo(
				id=2,
				pid=0,
				name="web-2",
				cmd="true",
				cwd="/",
				restart=False,
				started_at="",
				stdout_log="",
				stderr_log="",
				cluster="web",
				cluster_index=2,
			),
		]

		assert cluster_spec(members) == ScaleSpec(2, 2)
