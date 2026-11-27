"""Tests for container engine resolution and docker-backed processes"""

import contextlib
import os
import shlex
import signal

import pytest

import sentinel_core.process as process
from sentinel_core.docker import build_run_line, build_stop_command, container_name, resolve_engine
from sentinel_core.models import DockerConfig, ProcessInfo
from sentinel_core.process import managed_process, restart_process, start_process, stop_process
from sentinel_core.state import State


class TestResolveEngine:
	def test_explicit_engine_wins(self):
		assert resolve_engine("docker") == "docker"
		assert resolve_engine("podman") == "podman"

	def test_explicit_engine_must_be_known(self):
		with pytest.raises(ValueError, match="unknown container engine 'containerd'"):
			resolve_engine("containerd")

	def test_auto_detect_prefers_docker(self, monkeypatch):
		monkeypatch.setattr(
			"sentinel_core.docker.shutil.which", lambda name: f"/usr/bin/{name}" if name == "docker" else None
		)

		assert resolve_engine(None) == "docker"

	def test_auto_detect_falls_back_to_podman(self, monkeypatch):
		monkeypatch.setattr(
			"sentinel_core.docker.shutil.which", lambda name: f"/usr/bin/{name}" if name == "podman" else None
		)

		assert resolve_engine(None) == "podman"

	def test_auto_detect_without_any_engine_raises(self, monkeypatch):
		monkeypatch.setattr("sentinel_core.docker.shutil.which", lambda name: None)

		with pytest.raises(ValueError, match="no container engine found"):
			resolve_engine(None)


class TestContainerName:
	def test_single_process(self):
		assert container_name("web") == "sentinel-web"

	def test_cluster_instance(self):
		assert container_name("web-1") == "sentinel-web-1"


class TestBuildRunLine:
	def test_wraps_a_single_command_with_exec(self):
		line = build_run_line("docker", "web", "nginx:alpine", "nginx -g 'daemon off;'", ports=["8080:80"])

		assert line == " ".join(
			[
				"docker",
				"run",
				"--rm",
				"--name",
				"sentinel-web",
				"-p",
				"8080:80",
				"nginx:alpine",
				"sh",
				"-c",
				shlex.quote("exec nginx -g 'daemon off;'"),
			]
		)

	def test_compound_command_keeps_the_shell_without_exec(self):
		line = build_run_line("podman", "worker", "python:3.14", "python worker.py && sleep 30", volumes=["data:/data"])

		assert line == " ".join(
			[
				"podman",
				"run",
				"--rm",
				"--name",
				"sentinel-worker",
				"-v",
				"data:/data",
				"python:3.14",
				"sh",
				"-c",
				shlex.quote("python worker.py && sleep 30"),
			]
		)

	def test_quoting_survives_the_host_shell(self):
		tokens = shlex.split(build_run_line("docker", "web", "my image:tag", "sleep 30"))

		assert tokens[-4] == "my image:tag"
		assert tokens[-3:] == ["sh", "-c", "exec sleep 30"]


class TestBuildStopCommand:
	def test_stop_uses_the_recorded_grace(self):
		assert build_stop_command("docker", "web") == ["docker", "stop", "-t", "10", "sentinel-web"]

	def test_force_kills_the_container(self):
		assert build_stop_command("podman", "web", force=True) == ["podman", "kill", "sentinel-web"]


class TestDockerConfigRoundTrip:
	def test_round_trip(self):
		config = DockerConfig(image="nginx:alpine", ports=["8080:80"], volumes=["data:/data"], engine="docker")

		assert DockerConfig.from_dict(config.to_dict()) == config

	def test_defaults(self):
		config = DockerConfig(image="alpine")

		assert config.ports == []
		assert config.volumes == []
		assert config.engine is None

	def test_process_info_persists_the_docker_config(self):
		info = ProcessInfo(
			id=1,
			pid=2,
			name="web",
			cmd="docker run --rm --name sentinel-web alpine sh -c 'exec sleep 30'",
			cwd="/",
			restart=False,
			started_at="",
			stdout_log="",
			stderr_log="",
			docker=DockerConfig(image="alpine", engine="docker"),
		)

		assert ProcessInfo.from_dict(info.to_dict()).docker == DockerConfig(image="alpine", engine="docker")

	def test_legacy_state_without_docker_loads(self):
		data = {
			"id": 1,
			"pid": 2,
			"name": "web",
			"cmd": "true",
			"cwd": "/",
			"restart": False,
			"started_at": "",
			"stdout_log": "",
			"stderr_log": "",
		}

		assert ProcessInfo.from_dict(data).docker is None


@pytest.fixture(autouse=True)
def kill_leftover_containers(state: State):
	yield
	for info in State(state_dir=state.store.state_dir).list_processes():
		if info.pid > 0 and not info.stopped:
			with contextlib.suppress(ProcessLookupError, PermissionError):
				os.killpg(info.pid, signal.SIGKILL)


@pytest.fixture(autouse=True)
def short_container_stop_wait(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setattr(process, "_CONTAINER_STOP_WAIT_SECONDS", 0.3)


class TestDockerLifecycle:
	def test_start_records_the_docker_config(self, state: State, fake_engine):
		line = build_run_line("docker", "web", "alpine", "sleep 30", ports=["8080:80"])
		info = start_process(
			state, line, name="web", docker=DockerConfig(image="alpine", ports=["8080:80"], engine="docker")
		)

		assert info.cmd == line
		assert info.docker == DockerConfig(image="alpine", ports=["8080:80"], engine="docker")
		assert managed_process(info) is not None

	def test_stop_stops_the_container(self, state: State, fake_engine, wait_for, pid_is_gone):
		line = build_run_line("docker", "web", "alpine", "sleep 30")
		start_process(state, line, name="web", docker=DockerConfig(image="alpine", engine="docker"))
		# The fake engine publishes the wrapper pid only after its script settles; stopping before that is a no-op.
		wait_for(lambda: (fake_engine / f"{container_name('web')}.pid").exists())

		stopped = stop_process(state, "web")

		assert stopped.stopped
		wait_for(lambda: pid_is_gone(stopped.pid))

	def test_restart_respawns_the_container(self, state: State, fake_engine, wait_for):
		line = build_run_line("docker", "web", "alpine", "sleep 30")
		info = start_process(state, line, name="web", docker=DockerConfig(image="alpine", engine="docker"))
		wait_for(lambda: (fake_engine / f"{container_name('web')}.pid").exists())

		restarted = restart_process(state, "web")

		assert restarted.cmd == info.cmd
		assert restarted.docker == info.docker
		assert managed_process(restarted) is not None
