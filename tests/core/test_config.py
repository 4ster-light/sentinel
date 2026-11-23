"""Tests for the configuration file loader and the up reconciliation"""

import contextlib
import os
import signal
from pathlib import Path

import pytest

from sentinel_core.config import ConfigError, discover_config, load_config, run_up
from sentinel_core.docker import build_run_line
from sentinel_core.models import DockerConfig
from sentinel_core.process import managed_process, start_process, stop_process
from sentinel_core.state import State

TOML_STACK = """\
[processes.host]
cmd = "python app.py"
restart = true
env_file = ".env"
cwd = "/srv/app"
health_http = "http://localhost:8000/health"
health_interval = 10.0
health_timeout = 2.0
health_failures = 5
startup_timeout = 30
nice = 5
ionice = "best-effort:2"

[processes.box]
cmd = "nginx -g 'daemon off;'"
docker = { image = "nginx:alpine", ports = ["8080:80"], volumes = ["data:/data"], engine = "docker" }

[processes.farm]
cmd = "python worker.py"
scale = "2-4"
autoscale = ["cpu:80:40", "mem:800:300"]

[processes.pair]
cmd = "sleep 60"
instances = 2

[processes.late]
cmd = "sleep 60"
depends_on = ["host"]
"""

YAML_STACK = """\
processes:
  host:
    cmd: python app.py
    restart: true
    env_file: .env
    cwd: /srv/app
    health_http: http://localhost:8000/health
    health_interval: 10.0
    health_timeout: 2.0
    health_failures: 5
    startup_timeout: 30
    nice: 5
    ionice: best-effort:2
  box:
    cmd: nginx -g 'daemon off;'
    docker:
      image: nginx:alpine
      ports:
        - 8080:80
      volumes:
        - data:/data
      engine: docker
  farm:
    cmd: python worker.py
    scale: 2-4
    autoscale:
      - cpu:80:40
      - mem:800:300
  pair:
    cmd: sleep 60
    instances: 2
  late:
    cmd: sleep 60
    depends_on:
      - host
"""


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


class TestLoadConfig:
	def test_toml_and_yaml_stacks_parse_identically(self, tmp_path):
		toml_stack = write_stack(tmp_path, "stack.toml", TOML_STACK)
		yaml_stack = write_stack(tmp_path, "stack.yaml", YAML_STACK)

		assert load_config(toml_stack) == load_config(yaml_stack)

	def test_the_table_key_names_the_process(self, tmp_path):
		path = write_stack(tmp_path, "stack.toml", '[processes.web]\ncmd = "sleep 60"\n')

		specs = load_config(path)

		assert list(specs) == ["web"]
		assert specs["web"].cmd == "sleep 60"
		assert specs["web"].name == "web"

	def test_discovery_prefers_toml_over_yaml(self, tmp_path):
		write_stack(tmp_path, "sentinel.toml", '[processes.web]\ncmd = "sleep 60"\n')
		write_stack(tmp_path, "sentinel.yaml", "processes:\n  web:\n    cmd: sleep 61\n")
		write_stack(tmp_path, "sentinel.yml", "processes:\n  web:\n    cmd: sleep 62\n")

		assert discover_config() == tmp_path / "sentinel.toml"

	def test_discovery_falls_back_to_yaml_then_yml(self, tmp_path):
		write_stack(tmp_path, "sentinel.yaml", "processes:\n  web:\n    cmd: sleep 61\n")
		write_stack(tmp_path, "sentinel.yml", "processes:\n  web:\n    cmd: sleep 62\n")

		assert discover_config() == tmp_path / "sentinel.yaml"
		(tmp_path / "sentinel.yaml").unlink()

		assert discover_config() == tmp_path / "sentinel.yml"
		(tmp_path / "sentinel.yml").unlink()

		assert discover_config() is None

	def test_missing_file_is_rejected(self, tmp_path):
		with pytest.raises(ConfigError, match="does not exist"):
			load_config(tmp_path / "nope.toml")

	def test_unsupported_suffix_is_rejected(self, tmp_path):
		path = write_stack(tmp_path, "stack.json", "{}")

		with pytest.raises(ConfigError, match="Unsupported configuration format"):
			load_config(path)

	def test_invalid_toml_is_rejected(self, tmp_path):
		path = write_stack(tmp_path, "stack.toml", "processes = [\n")

		with pytest.raises(ConfigError, match="Invalid TOML"):
			load_config(path)

	def test_invalid_yaml_is_rejected(self, tmp_path):
		path = write_stack(tmp_path, "stack.yaml", "processes:\n  web:\n   cmd: [unclosed\n")

		with pytest.raises(ConfigError, match="Invalid YAML"):
			load_config(path)

	def test_unknown_root_key_is_rejected(self, tmp_path):
		path = write_stack(tmp_path, "stack.toml", 'title = "stack"\n\n[processes.web]\ncmd = "sleep 60"\n')

		with pytest.raises(ConfigError, match="unknown root key 'title'"):
			load_config(path)

	def test_missing_processes_table_is_rejected(self, tmp_path):
		path = write_stack(tmp_path, "stack.toml", 'title = "stack"\n')

		with pytest.raises(ConfigError, match="must define a 'processes' table"):
			load_config(path)

	def test_empty_processes_table_is_rejected(self, tmp_path):
		path = write_stack(tmp_path, "stack.toml", "[processes]\n")

		with pytest.raises(ConfigError, match="at least one process"):
			load_config(path)

	def test_unknown_process_key_is_rejected(self, tmp_path):
		path = write_stack(tmp_path, "stack.toml", '[processes.web]\ncmd = "sleep 60"\ncolor = "blue"\n')

		with pytest.raises(ConfigError, match="unknown key 'color'"):
			load_config(path)

	def test_name_key_is_rejected(self, tmp_path):
		path = write_stack(tmp_path, "stack.toml", '[processes.web]\nname = "other"\ncmd = "sleep 60"\n')

		with pytest.raises(ConfigError, match="already names the process"):
			load_config(path)

	def test_missing_cmd_is_rejected(self, tmp_path):
		path = write_stack(tmp_path, "stack.toml", "[processes.web]\nrestart = true\n")

		with pytest.raises(ConfigError, match="'cmd' is required"):
			load_config(path)

	def test_cmd_must_be_a_string(self, tmp_path):
		path = write_stack(tmp_path, "stack.toml", "[processes.web]\ncmd = 5\n")

		with pytest.raises(ConfigError, match="'cmd' must be a string"):
			load_config(path)

	def test_restart_must_be_a_boolean(self, tmp_path):
		path = write_stack(tmp_path, "stack.toml", '[processes.web]\ncmd = "sleep 60"\nrestart = "yes"\n')

		with pytest.raises(ConfigError, match="'restart' must be a boolean"):
			load_config(path)

	def test_instances_rejects_a_boolean(self, tmp_path):
		path = write_stack(tmp_path, "stack.toml", '[processes.web]\ncmd = "sleep 60"\ninstances = true\n')

		with pytest.raises(ConfigError, match="'instances' must be an integer"):
			load_config(path)

	def test_health_interval_rejects_a_boolean(self, tmp_path):
		path = write_stack(tmp_path, "stack.toml", '[processes.web]\ncmd = "sleep 60"\nhealth_interval = true\n')

		with pytest.raises(ConfigError, match="'health_interval' must be a number"):
			load_config(path)

	def test_depends_on_must_be_a_list_of_strings(self, tmp_path):
		path = write_stack(tmp_path, "stack.toml", '[processes.web]\ncmd = "sleep 60"\ndepends_on = "db"\n')

		with pytest.raises(ConfigError, match="'depends_on' must be a list of strings"):
			load_config(path)

	def test_scale_must_be_a_string(self, tmp_path):
		path = write_stack(tmp_path, "stack.toml", '[processes.web]\ncmd = "sleep 60"\nscale = 3\n')

		with pytest.raises(ConfigError, match="'scale' must be a string"):
			load_config(path)

	def test_docker_must_be_a_table(self, tmp_path):
		path = write_stack(tmp_path, "stack.toml", '[processes.web]\ncmd = "sleep 60"\ndocker = "nginx:alpine"\n')

		with pytest.raises(ConfigError, match="'docker' must be a table"):
			load_config(path)

	def test_docker_image_is_required(self, tmp_path):
		path = write_stack(
			tmp_path, "stack.toml", '[processes.web]\ncmd = "sleep 60"\ndocker = { ports = ["8080:80"] }\n'
		)

		with pytest.raises(ConfigError, match=r"'docker.image' is required"):
			load_config(path)

	def test_unknown_docker_key_is_rejected(self, tmp_path):
		path = write_stack(
			tmp_path, "stack.toml", '[processes.web]\ncmd = "sleep 60"\ndocker = { image = "alpine", replicas = 2 }\n'
		)

		with pytest.raises(ConfigError, match="unknown docker key 'replicas'"):
			load_config(path)

	def test_docker_ports_must_be_a_list_of_strings(self, tmp_path):
		path = write_stack(
			tmp_path,
			"stack.toml",
			'[processes.web]\ncmd = "sleep 60"\ndocker = { image = "alpine", ports = "8080:80" }\n',
		)

		with pytest.raises(ConfigError, match=r"'docker.ports' must be a list of strings"):
			load_config(path)

	def test_validate_conflicts_cite_the_process(self, tmp_path):
		path = write_stack(
			tmp_path, "stack.toml", '[processes.web]\ncmd = "sleep 60"\nuser = "aster"\ndocker = { image = "alpine" }\n'
		)

		with pytest.raises(ConfigError, match=r"process 'web'.*cannot be combined"):
			load_config(path)

	def test_docker_engine_validation_is_cited(self, tmp_path):
		path = write_stack(
			tmp_path,
			"stack.toml",
			'[processes.web]\ncmd = "sleep 60"\ndocker = { image = "alpine", engine = "containerd" }\n',
		)

		with pytest.raises(ConfigError, match=r"process 'web'.*docker-engine must be docker or podman"):
			load_config(path)


@pytest.fixture(autouse=True)
def kill_leftover_processes(state: State):
	yield
	for info in State(state_dir=state.store.state_dir).list_processes():
		if info.pid > 0 and not info.stopped:
			with contextlib.suppress(ProcessLookupError, PermissionError):
				os.killpg(info.pid, signal.SIGKILL)


class TestRunUp:
	def test_starts_a_fresh_stack_in_dependency_order(self, state: State, tmp_path):
		path = write_stack(tmp_path, "stack.toml", FRESH_STACK)

		report = run_up(state, path, load_config(path))

		assert [info.name for info in report.started] == ["db", "web"]
		assert report.expected == ["db", "web"]
		assert report.skipped_running == []
		assert report.conflicts == []
		assert report.failed == []
		for name in ("db", "web"):
			info = state.find_process_by_name(name)
			assert info is not None
			assert managed_process(info) is not None

	def test_a_second_run_skips_running_processes(self, state: State, tmp_path):
		path = write_stack(tmp_path, "stack.toml", FRESH_STACK)
		run_up(state, path, load_config(path))
		pids = {info.name: info.pid for info in state.list_processes()}

		report = run_up(state, path, load_config(path))

		assert report.started == []
		assert report.skipped_running == ["db", "web"]
		assert {info.name: info.pid for info in state.list_processes()} == pids

	def test_restarts_a_stopped_process_with_its_recorded_settings(self, state: State, tmp_path):
		path = write_stack(tmp_path, "stack.toml", FRESH_STACK)
		run_up(state, path, load_config(path))
		stopped = stop_process(state, "web")

		report = run_up(state, path, load_config(path))

		assert [info.name for info in report.started] == ["web"]
		assert report.skipped_running == ["db"]
		restarted = state.find_process_by_name("web")
		assert restarted is not None
		assert restarted.pid != stopped.pid
		assert managed_process(restarted) is not None

	def test_reports_a_conflict_when_the_recorded_cmd_differs(self, state: State, tmp_path):
		start_process(state, "sleep 999", name="web")
		path = write_stack(tmp_path, "stack.toml", '[processes.web]\ncmd = "sleep 300"\n')

		report = run_up(state, path, load_config(path))

		assert report.conflicts == [("web", "sleep 999")]
		assert report.started == []
		existing = state.find_process_by_name("web")
		assert existing is not None
		assert existing.cmd == "sleep 999"

	def test_auto_creates_groups_idempotently(self, state: State, tmp_path):
		path = write_stack(tmp_path, "stack.toml", '[processes.web]\ncmd = "sleep 300"\ngroup = "api"\n')

		first = run_up(state, path, load_config(path))

		assert first.groups_created == ["api"]
		info = state.find_process_by_name("web")
		assert info is not None
		assert info.group == "api"

		second = run_up(state, path, load_config(path))

		assert second.groups_created == []
		assert state.get_group("api") is not None
		assert second.skipped_running == ["web"]

	def test_a_dependency_on_a_clustered_process_is_rejected(self, state: State, tmp_path):
		path = write_stack(
			tmp_path,
			"stack.toml",
			'[processes.db]\ncmd = "sleep 300"\ninstances = 2\n\n[processes.web]\ncmd = "sleep 300"\ndepends_on = ["db"]\n',
		)

		with pytest.raises(ConfigError, match="cannot depend on the clustered process 'db'"):
			run_up(state, path, load_config(path))

		assert state.list_processes() == []

	def test_an_unknown_dependency_is_rejected(self, state: State, tmp_path):
		path = write_stack(tmp_path, "stack.toml", '[processes.web]\ncmd = "sleep 300"\ndepends_on = ["ghost"]\n')

		with pytest.raises(ConfigError, match="neither in the file nor recorded"):
			run_up(state, path, load_config(path))

		assert state.list_processes() == []

	def test_a_stopped_dependency_outside_the_file_fails_cleanly(self, state: State, tmp_path):
		start_process(state, "sleep 999", name="db")
		stop_process(state, "db")
		path = write_stack(tmp_path, "stack.toml", '[processes.web]\ncmd = "sleep 300"\ndepends_on = ["db"]\n')

		with pytest.raises(ConfigError, match="neither in this batch nor running"):
			run_up(state, path, load_config(path))

		assert state.find_process_by_name("web") is None
		db_info = state.find_process_by_name("db")
		assert db_info is not None
		assert db_info.stopped

	def test_cluster_expansion_colliding_with_a_table_key_is_rejected(self, state: State, tmp_path):
		path = write_stack(
			tmp_path,
			"stack.toml",
			'[processes.farm]\ncmd = "sleep 300"\nscale = "1-2"\n\n[processes.farm-1]\ncmd = "sleep 300"\n',
		)

		with pytest.raises(ConfigError, match="'farm-1' is defined twice"):
			run_up(state, path, load_config(path))

	def test_starts_a_docker_spec_through_the_engine(self, state: State, fake_engine, tmp_path):
		path = write_stack(
			tmp_path,
			"stack.toml",
			'[processes.web]\ncmd = "sleep 300"\ndocker = { image = "alpine", ports = ["8080:80"] }\n',
		)

		report = run_up(state, path, load_config(path))

		assert [info.name for info in report.started] == ["web"]
		info = state.find_process_by_name("web")
		assert info is not None
		assert info.cmd == build_run_line("docker", "web", "alpine", "sleep 300", ports=["8080:80"])
		assert info.docker == DockerConfig(image="alpine", ports=["8080:80"], engine="docker")
		assert managed_process(info) is not None

	def test_scale_starts_the_minimum_with_cluster_fields(self, state: State, tmp_path):
		path = write_stack(tmp_path, "stack.toml", '[processes.farm]\ncmd = "sleep 300"\nscale = "1-3"\n')

		report = run_up(state, path, load_config(path))

		assert [info.name for info in report.started] == ["farm-1"]
		assert report.expected == ["farm-1"]
		info = state.find_process_by_name("farm-1")
		assert info is not None
		assert info.cluster == "farm"
		assert info.cluster_index == 1
		assert info.cluster_min == 1
		assert info.cluster_max == 3
