"""Integration tests that run a real container when an engine is available"""

import contextlib
import os
import signal
import subprocess

import pytest

from sentinel_core.docker import build_run_line, container_name, resolve_engine
from sentinel_core.models import DockerConfig
from sentinel_core.process import start_process, stop_process
from sentinel_core.state import State

INTEGRATION_IMAGE = "alpine:latest"


def _engine_available() -> str | None:
	try:
		engine = resolve_engine(None)
	except ValueError:
		return None
	try:
		subprocess.run([engine, "run", "--rm", INTEGRATION_IMAGE, "true"], capture_output=True, check=True, timeout=180)
	except OSError, subprocess.SubprocessError:
		return None
	return engine


@pytest.fixture(scope="module")
def real_engine() -> str:
	engine = _engine_available()
	if engine is None:
		pytest.skip("no working container engine available")
	return engine


@pytest.fixture(autouse=True)
def kill_leftover_containers(state: State, real_engine: str):
	yield
	for info in State(state_dir=state.store.state_dir).list_processes():
		if info.pid > 0 and not info.stopped:
			with contextlib.suppress(OSError, subprocess.SubprocessError):
				subprocess.run(
					[real_engine, "rm", "-f", container_name(info.name)],
					capture_output=True,
					check=False,
					timeout=30,
				)
			with contextlib.suppress(ProcessLookupError, PermissionError):
				os.killpg(info.pid, signal.SIGKILL)


def _container_is_up(engine: str, name: str) -> bool:
	result = subprocess.run(
		[engine, "ps", "--filter", f"name=^{name}$", "--format", "{{.Names}}"],
		capture_output=True,
		text=True,
		check=False,
		timeout=30,
	)
	return result.returncode == 0 and name in result.stdout.split()


class TestRealContainerLifecycle:
	def test_run_and_stop_a_real_container(self, state: State, real_engine: str, wait_for, pid_is_gone):
		line = build_run_line(real_engine, "docker-it", INTEGRATION_IMAGE, "sleep 30")
		start_process(
			state,
			line,
			name="docker-it",
			docker=DockerConfig(image=INTEGRATION_IMAGE, engine=real_engine),
		)

		wait_for(lambda: _container_is_up(real_engine, container_name("docker-it")))

		stopped = stop_process(state, "docker-it")

		assert stopped.stopped
		assert pid_is_gone(stopped.pid)
