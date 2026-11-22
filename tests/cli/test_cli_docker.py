"""Tests for the docker flags on the run command"""

import contextlib
import os
import signal

import pytest
from typer.testing import CliRunner

from sentinel_cli import app
from sentinel_core.docker import build_run_line
from sentinel_core.models import DockerConfig
from sentinel_core.state import State

runner = CliRunner()


@pytest.fixture(autouse=True)
def kill_started_containers(state: State):
	yield
	for info in State(state_dir=state.store.state_dir).list_processes():
		if info.pid > 0 and not info.stopped:
			with contextlib.suppress(ProcessLookupError, PermissionError):
				os.killpg(info.pid, signal.SIGKILL)


class TestRunDockerFlags:
	def test_run_wraps_the_command_for_the_container(self, state: State, fake_engine):
		args = ["run", "sleep 30", "--name", "web", "--docker-image", "alpine", "--docker-ports", "8080:80"]
		result = runner.invoke(app, args)

		assert result.exit_code == 0, result.output
		info = State().find_process_by_name("web")
		assert info is not None
		assert info.docker == DockerConfig(image="alpine", ports=["8080:80"], engine="docker")
		assert info.cmd == build_run_line("docker", "web", "alpine", "sleep 30", ports=["8080:80"])

	def test_run_without_a_name_uses_the_image_name(self, state: State, fake_engine):
		result = runner.invoke(app, ["run", "sleep 30", "--docker-image", "docker.io/library/alpine:latest"])

		assert result.exit_code == 0, result.output
		info = State().find_process_by_name("alpine")
		assert info is not None
		assert "--name sentinel-alpine" in info.cmd

	def test_docker_image_rejects_host_only_flags(self, state: State):
		result = runner.invoke(app, ["run", "sleep 30", "--docker-image", "alpine", "--user", "root"])

		assert result.exit_code == 1
		assert "cannot be combined" in result.stderr
		assert State().list_processes() == []

	def test_docker_ports_require_an_image(self, state: State):
		result = runner.invoke(app, ["run", "sleep 30", "--docker-ports", "8080:80"])

		assert result.exit_code == 1
		assert "require --docker-image" in result.stderr
		assert State().list_processes() == []

	def test_unknown_docker_engine_is_rejected(self, state: State):
		result = runner.invoke(app, ["run", "sleep 30", "--docker-image", "alpine", "--docker-engine", "containerd"])

		assert result.exit_code == 1
		assert "--docker-engine must be docker or podman" in result.stderr
		assert State().list_processes() == []

	def test_missing_engine_reports_an_error(self, state: State, monkeypatch):
		monkeypatch.setenv("PATH", "")

		result = runner.invoke(app, ["run", "sleep 30", "--docker-image", "alpine"])

		assert result.exit_code == 1
		assert "no container engine found" in result.stderr
		assert State().list_processes() == []


class TestDockerStatusDisplay:
	def test_status_shows_the_container(self, state: State, fake_engine):
		runner.invoke(app, ["run", "sleep 30", "--name", "web", "--docker-image", "alpine"])

		result = runner.invoke(app, ["status", "web"])

		assert result.exit_code == 0, result.output
		assert "Docker:" in result.stdout
		assert "alpine" in result.stdout
		assert "(docker)" in result.stdout

	def test_stop_stops_the_container(self, state: State, fake_engine):
		runner.invoke(app, ["run", "sleep 30", "--name", "web", "--docker-image", "alpine"])

		result = runner.invoke(app, ["stop", "web"])

		assert result.exit_code == 0, result.output
		stopped = State().find_process_by_name("web")
		assert stopped is not None
		assert stopped.stopped
