"""Tests for the up command"""

import contextlib
import os
import signal
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sentinel_cli import app
from sentinel_core.docker import build_run_line
from sentinel_core.models import DockerConfig
from sentinel_core.state import State

runner = CliRunner()


FRESH_STACK = """\
[processes.db]
cmd = "sleep 300"

[processes.web]
cmd = "sleep 300"
depends_on = ["db"]
"""


def write_stack(tmp_path: Path, filename: str, content: str) -> Path:
	path = tmp_path / filename
	path.write_text(content)
	return path


@pytest.fixture(autouse=True)
def kill_started_processes(state: State):
	yield
	for info in State(state_dir=state.store.state_dir).list_processes():
		if info.pid > 0 and not info.stopped:
			with contextlib.suppress(ProcessLookupError, PermissionError):
				os.killpg(info.pid, signal.SIGKILL)


class TestUp:
	def test_starts_a_fresh_stack(self, state: State, tmp_path):
		config = write_stack(tmp_path, "stack.toml", FRESH_STACK)

		result = runner.invoke(app, ["up", "--config", str(config)])

		assert result.exit_code == 0, result.output
		assert "Started db" in result.stdout
		assert "Started web" in result.stdout
		for name in ("db", "web"):
			info = State().find_process_by_name(name)
			assert info is not None
			assert not info.stopped

	def test_a_second_up_keeps_the_same_pids(self, state: State, tmp_path):
		config = write_stack(tmp_path, "stack.toml", FRESH_STACK)
		runner.invoke(app, ["up", "--config", str(config)])
		pids = {info.name: info.pid for info in State().list_processes()}

		result = runner.invoke(app, ["up", "--config", str(config)])

		assert result.exit_code == 0, result.output
		assert "already running" in result.stdout
		assert {info.name: info.pid for info in State().list_processes()} == pids

	def test_restarts_a_stopped_process(self, state: State, tmp_path):
		config = write_stack(tmp_path, "stack.toml", FRESH_STACK)
		runner.invoke(app, ["up", "--config", str(config)])
		runner.invoke(app, ["stop", "web"])

		result = runner.invoke(app, ["up", "--config", str(config)])

		assert result.exit_code == 0, result.output
		assert "Started web" in result.stdout
		assert "already running" in result.stdout
		info = State().find_process_by_name("web")
		assert info is not None
		assert not info.stopped

	def test_warns_when_the_definition_differs(self, state: State, tmp_path):
		runner.invoke(app, ["run", "sleep 999", "--name", "web"])
		config = write_stack(tmp_path, "stack.toml", '[processes.web]\ncmd = "sleep 300"\n')

		result = runner.invoke(app, ["up", "--config", str(config)])

		assert result.exit_code == 0, result.output
		assert "different command" in result.stdout
		info = State().find_process_by_name("web")
		assert info is not None
		assert info.cmd == "sleep 999"

	def test_a_broken_file_starts_nothing(self, state: State, tmp_path):
		config = write_stack(tmp_path, "stack.toml", '[processes.web]\ncmd = "sleep 60"\ncolor = "blue"\n')

		result = runner.invoke(app, ["up", "--config", str(config)])

		assert result.exit_code == 1
		assert "unknown key 'color'" in result.stderr
		assert State().list_processes() == []

	def test_discovery_without_a_file_reports_how_to_pass_one(self, state: State):
		result = runner.invoke(app, ["up"])

		assert result.exit_code == 1
		assert "No configuration file found" in result.stderr

	def test_a_missing_explicit_config_is_rejected(self, state: State, tmp_path):
		result = runner.invoke(app, ["up", "--config", str(tmp_path / "nope.toml")])

		assert result.exit_code == 1
		assert "does not exist" in " ".join(result.stderr.split())

	def test_reads_a_yaml_file(self, state: State, tmp_path):
		config = write_stack(tmp_path, "stack.yaml", "processes:\n  db:\n    cmd: sleep 300\n")

		result = runner.invoke(app, ["up", "--config", str(config)])

		assert result.exit_code == 0, result.output
		assert "Started db" in result.stdout
		assert State().find_process_by_name("db") is not None

	def test_starts_a_docker_spec(self, state: State, fake_engine, tmp_path):
		config = write_stack(
			tmp_path,
			"stack.toml",
			'[processes.web]\ncmd = "sleep 300"\ndocker = { image = "alpine", ports = ["8080:80"] }\n',
		)

		result = runner.invoke(app, ["up", "--config", str(config)])

		assert result.exit_code == 0, result.output
		info = State().find_process_by_name("web")
		assert info is not None
		assert info.cmd == build_run_line("docker", "web", "alpine", "sleep 300", ports=["8080:80"])
		assert info.docker == DockerConfig(image="alpine", ports=["8080:80"], engine="docker")
