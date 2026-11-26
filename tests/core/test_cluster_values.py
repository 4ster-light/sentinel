"""Value tests for the cluster instance helpers"""

from types import SimpleNamespace
from typing import cast

import pytest

import sentinel_core.cluster as cluster
from sentinel_core.cluster import ScaleSpec, cluster_members, cluster_spec, scale_cluster
from sentinel_core.models import AutoscaleConfig, DockerConfig, HealthCheckConfig, ProcessInfo
from sentinel_core.state import State


def member(
	name: str,
	index: int | None = None,
	*,
	minimum: int | None = None,
	maximum: int | None = None,
	group_name: str = "web",
) -> ProcessInfo:
	return ProcessInfo(
		id=index or 0,
		pid=0,
		name=name,
		cmd="python app.py",
		cwd="/srv/app",
		restart=False,
		started_at="",
		stdout_log="",
		stderr_log="",
		cluster=group_name,
		cluster_index=index,
		cluster_min=minimum,
		cluster_max=maximum,
	)


def fake_state(members: list[ProcessInfo]) -> State:
	removed: list[int] = []
	state = SimpleNamespace(list_processes=lambda: list(members), remove_process=removed.append)
	return cast(State, SimpleNamespace(**vars(state)))


class TestClusterMembers:
	def test_filters_by_cluster_and_sorts_by_index(self) -> None:
		state = fake_state(
			[member("web-2", 2), member("web-1", 1), member("other", None, minimum=1, maximum=1, group_name="other")]
		)

		assert [p.name for p in cluster_members(state, "web")] == ["web-1", "web-2"]

	def test_reads_the_recorded_range(self) -> None:
		members = [member("web-1", 1, minimum=2, maximum=4)]

		assert cluster_spec(members) == ScaleSpec(2, 4)

	def test_falls_back_to_the_member_count(self) -> None:
		members = [member("web-1", 1), member("web-2", 2)]

		assert cluster_spec(members) == ScaleSpec(2, 2)


class TestStartInstance:
	def test_passes_every_template_field(self, monkeypatch: pytest.MonkeyPatch) -> None:
		calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
		sentinel = member("web-2", 2)
		monkeypatch.setattr(
			cluster,
			"start_process",
			lambda *args, **kwargs: calls.append((args, kwargs)) or sentinel,
		)
		template = member("web-1", 1, minimum=2, maximum=4)
		template.base_env = {"A": "1"}
		template.env = {"B": "2"}
		template.group = "staff"
		template.user = "alice"
		template.env_file = ".env"
		template.restart = True
		template.health_check = HealthCheckConfig(
			kind="tcp", target="localhost:9000", interval_seconds=10.0, timeout_seconds=2.0, failure_threshold=3
		)
		template.startup_timeout_seconds = 30.0
		template.nice = 5
		template.ionice_ioclass = "best_effort"
		template.ionice_value = 2
		template.depends_on = ["db"]
		template.autoscale = AutoscaleConfig(cpu_high=80.0, cpu_low=40.0)
		template.docker = DockerConfig(image="nginx", ports=[], volumes=[], engine="docker")
		state = fake_state([])

		assert cluster._start_instance(state, template, "web-2", 2) is sentinel

		args, kwargs = calls[0]
		assert args == (state, "python app.py")
		assert kwargs == {
			"name": "web-2",
			"base_env": {"A": "1"},
			"group": "staff",
			"restart": True,
			"user": "alice",
			"env": {"B": "2"},
			"env_file": ".env",
			"cwd": "/srv/app",
			"health_check": template.health_check,
			"startup_timeout_seconds": 30.0,
			"nice": 5,
			"ionice_ioclass": "best_effort",
			"ionice_value": 2,
			"depends_on": ["db"],
			"cluster": "web",
			"cluster_index": 2,
			"cluster_min": 2,
			"cluster_max": 4,
			"autoscale": template.autoscale,
			"docker": template.docker,
		}


class TestScaleCluster:
	def test_shrinks_to_the_desired_count(self, monkeypatch: pytest.MonkeyPatch) -> None:
		members = [member("web-1", 1, minimum=2, maximum=4), member("web-2", 2, minimum=2, maximum=4)]
		members.append(member("web-3", 3, minimum=2, maximum=4))
		state = fake_state(members)
		stopped: list[tuple[int, bool]] = []
		monkeypatch.setattr(
			cluster,
			"stop_process",
			lambda state, ident, force=False: stopped.append((ident, force)) or members[ident - 1],
		)

		result = scale_cluster(state, "web", 2)

		assert [p.name for p in result.stopped] == ["web-3"]
		assert result.started == []
		assert stopped == [(3, False)]

	def test_grows_to_the_desired_count(self, monkeypatch: pytest.MonkeyPatch) -> None:
		members = [member("web-1", 1, minimum=2, maximum=4), member("web-2", 2, minimum=2, maximum=4)]
		state = fake_state(members)
		started: list[tuple[str, int]] = []
		monkeypatch.setattr(
			cluster,
			"_start_instance",
			lambda state, template, name, index: started.append((name, index)) or member(name, index),
		)

		result = scale_cluster(state, "web", 3)

		assert started == [("web-3", 3)]
		assert [p.name for p in result.started] == ["web-3"]
		assert result.stopped == []

	def test_rejects_an_unknown_cluster(self) -> None:
		state = fake_state([])

		with pytest.raises(ValueError, match="Unknown cluster 'web'"):
			scale_cluster(state, "web", 2)

	def test_rejects_a_count_outside_the_range(self) -> None:
		state = fake_state([member("web-1", 1, minimum=2, maximum=4)])

		with pytest.raises(ValueError, match=r"allows 2-4 instances, not 5"):
			scale_cluster(state, "web", 5)
