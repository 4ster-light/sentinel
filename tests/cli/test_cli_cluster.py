"""Tests for cluster scale ranges and the cluster commands"""

import pytest
from typer.testing import CliRunner

from sentinel_cli import app
from sentinel_core.cluster import cluster_members
from sentinel_core.process import batch_stop_processes
from sentinel_core.state import State

runner = CliRunner()


@pytest.fixture(autouse=True)
def stop_cluster_processes(state: State):
	yield
	batch_stop_processes(state, state.list_processes(), force=True)


def start_cluster(minimum: int = 2, maximum: int = 4, name: str = "web") -> None:
	result = runner.invoke(app, ["run", "sleep 30", "--name", name, "--scale", f"{minimum}-{maximum}"])
	assert result.exit_code == 0, result.output


def member_names(name: str = "web") -> list[str]:
	return [info.name for info in cluster_members(State(), name)]


class TestRunScale:
	def test_scale_range_starts_the_minimum_instances(self, state: State):
		start_cluster(2, 4)

		reloaded = State()
		first = reloaded.find_process_by_name("web-1")
		second = reloaded.find_process_by_name("web-2")

		assert first is not None
		assert second is not None
		assert reloaded.find_process_by_name("web-3") is None
		assert (first.cluster, first.cluster_min, first.cluster_max) == ("web", 2, 4)
		assert (second.cluster_index, second.cluster_min, second.cluster_max) == (2, 2, 4)

	def test_single_number_is_a_fixed_size_cluster(self, state: State):
		result = runner.invoke(app, ["run", "sleep 30", "--name", "fixed", "--scale", "2"])

		assert result.exit_code == 0, result.output
		assert member_names("fixed") == ["fixed-1", "fixed-2"]
		info = State().find_process_by_name("fixed-1")
		assert info is not None
		assert (info.cluster_min, info.cluster_max) == (2, 2)

	def test_invalid_range_is_rejected_before_starting(self, state: State):
		result = runner.invoke(app, ["run", "sleep 30", "--name", "web", "--scale", "4-2"])

		assert result.exit_code == 1
		assert "scale maximum 2 is below the minimum 4" in result.stderr
		assert State().find_process_by_name("web-1") is None

	def test_scale_cannot_combine_with_instances(self, state: State):
		result = runner.invoke(
			app,
			["run", "sleep 30", "--name", "web", "--scale", "2-4", "--instances", "2"],
		)

		assert result.exit_code == 1
		assert "--scale cannot be combined with --instances" in result.stderr

	def test_scale_cannot_combine_with_depends_on(self, state: State):
		result = runner.invoke(
			app,
			["run", "sleep 30", "--name", "web", "--scale", "2-4", "--depends-on", "db"],
		)

		assert result.exit_code == 1
		assert "--scale cannot be combined with --depends-on" in result.stderr


class TestClusterCommands:
	def test_list_reports_instances_and_range(self, state: State):
		start_cluster(2, 4)

		result = runner.invoke(app, ["cluster", "list"])

		assert result.exit_code == 0
		assert "web" in result.stdout
		assert "2-4" in result.stdout

	def test_list_without_clusters(self, state: State):
		result = runner.invoke(app, ["cluster", "list"])

		assert result.exit_code == 0
		assert "No clusters found" in result.stdout

	def test_scale_up_starts_missing_instances(self, state: State):
		start_cluster(2, 4)

		result = runner.invoke(app, ["cluster", "scale", "web", "4"])

		assert result.exit_code == 0, result.output
		assert "Started web-3" in result.stdout
		assert member_names() == ["web-1", "web-2", "web-3", "web-4"]

	def test_scale_down_stops_and_removes_instances(self, state: State):
		start_cluster(2, 4)
		runner.invoke(app, ["cluster", "scale", "web", "4"])

		result = runner.invoke(app, ["cluster", "scale", "web", "2"])

		assert result.exit_code == 0, result.output
		assert "Stopped web-4" in result.stdout
		assert member_names() == ["web-1", "web-2"]
		assert State().find_process_by_name("web-4") is None

	def test_scale_outside_the_range_is_rejected(self, state: State):
		start_cluster(2, 4)

		result = runner.invoke(app, ["cluster", "scale", "web", "5"])

		assert result.exit_code == 1
		assert "allows 2-4 instances, not 5" in result.stdout

	def test_unknown_cluster_is_rejected(self, state: State):
		result = runner.invoke(app, ["cluster", "scale", "web", "2"])

		assert result.exit_code == 1
		assert "Unknown cluster 'web'" in result.stdout

	def test_restart_keeps_a_process_in_its_cluster(self, state: State):
		start_cluster(2, 4)

		result = runner.invoke(app, ["restart", "web-1"])

		assert result.exit_code == 0, result.output
		info = State().find_process_by_name("web-1")
		assert info is not None
		assert (info.cluster, info.cluster_min, info.cluster_max) == ("web", 2, 4)
