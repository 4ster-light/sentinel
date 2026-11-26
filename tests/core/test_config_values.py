"""Value tests for the configuration loader"""

from pathlib import Path

import pytest

from sentinel_core.cluster import ScaleSpec
from sentinel_core.config import ConfigError, _template, load_config
from sentinel_core.models import DockerConfig
from sentinel_core.options import StartOptions
from sentinel_core.state import HealthCheckConfig


def write_config(tmp_path: Path, content: str) -> Path:
	path = tmp_path / "sentinel.toml"
	path.write_text(content)
	return path


FULL_PROCESS = """\
[processes.api]
cmd = "python app.py"
restart = true
user = "alice"
group = "staff"
env_file = ".env"
cwd = "/srv/app"
health_http = "http://localhost:8000/health"
health_interval = 10.0
health_timeout = 2.0
health_failures = 5
startup_timeout = 30
instances = 2
nice = 5
ionice = "best-effort:2"
"""


class TestProcessOptions:
	def test_maps_every_process_key(self, tmp_path: Path) -> None:
		path = write_config(tmp_path, FULL_PROCESS)

		options = load_config(path)["api"]

		assert options == StartOptions(
			cmd="python app.py",
			name="api",
			restart=True,
			user="alice",
			group="staff",
			env_file=".env",
			cwd="/srv/app",
			health_http="http://localhost:8000/health",
			health_interval=10.0,
			health_timeout=2.0,
			health_failures=5,
			startup_timeout_seconds=30,
			instances=2,
			nice=5,
			ionice="best-effort:2",
		)

	def test_applies_the_documented_defaults(self, tmp_path: Path) -> None:
		path = write_config(tmp_path, '[processes.api]\ncmd = "true"\n')

		options = load_config(path)["api"]

		assert options == StartOptions(cmd="true", name="api")

	def test_maps_the_tcp_health_target(self, tmp_path: Path) -> None:
		path = write_config(tmp_path, '[processes.api]\ncmd = "true"\nhealth_tcp = "localhost:9000"\n')

		options = load_config(path)["api"]

		assert options.health_tcp == "localhost:9000"
		assert options.health_http is None

	def test_maps_a_clustered_process(self, tmp_path: Path) -> None:
		content = """\
[processes.db]
cmd = "sleep 300"

[processes.web]
cmd = "python web.py"
scale = "2-4"
autoscale = ["cpu:80:40", "mem:800:300"]

[processes.late]
cmd = "sleep 60"
depends_on = ["db"]
"""
		path = write_config(tmp_path, content)

		specs = load_config(path)

		assert specs["web"] == StartOptions(
			cmd="python web.py",
			name="web",
			scale="2-4",
			autoscale=["cpu:80:40", "mem:800:300"],
		)
		assert specs["late"] == StartOptions(cmd="sleep 60", name="late", depends_on=["db"])


class TestDockerOptions:
	def test_maps_the_full_docker_table(self, tmp_path: Path) -> None:
		content = """\
[processes.box]
cmd = "nginx"
docker = { image = "nginx:alpine", ports = ["8080:80"], volumes = ["data:/data"], engine = "podman" }
"""
		path = write_config(tmp_path, content)

		options = load_config(path)["box"]

		assert options == StartOptions(
			cmd="nginx",
			name="box",
			docker_image="nginx:alpine",
			docker_ports=["8080:80"],
			docker_volumes=["data:/data"],
			docker_engine="podman",
		)

	def test_defaults_the_optional_docker_keys(self, tmp_path: Path) -> None:
		content = '[processes.box]\ncmd = "nginx"\ndocker = { image = "nginx" }\n'
		path = write_config(tmp_path, content)

		options = load_config(path)["box"]

		assert options == StartOptions(cmd="nginx", name="box", docker_image="nginx")


class TestTemplate:
	def test_builds_a_host_process(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.chdir(tmp_path)
		options = StartOptions(
			cmd="python app.py",
			name="api",
			restart=True,
			user="alice",
			group="staff",
			env_file=".env",
			health_http="http://localhost:8000/health",
			health_interval=10.0,
			health_timeout=2.0,
			health_failures=5,
			startup_timeout_seconds=30.0,
			nice=5,
			ionice="best-effort:2",
			depends_on=["db"],
		)

		info = _template(7, "api", "api", 1, options, None, "python app.py", None)

		assert info.id == 7
		assert info.pid == 0
		assert info.name == "api"
		assert info.cmd == "python app.py"
		assert info.cwd == str(tmp_path.resolve())
		assert info.restart is True
		assert info.started_at == ""
		assert info.stdout_log == ""
		assert info.stderr_log == ""
		assert info.user == "alice"
		assert info.group == "staff"
		assert info.depends_on == ["db"]
		assert info.cluster is None
		assert info.cluster_index is None
		assert info.cluster_min is None
		assert info.cluster_max is None
		assert info.autoscale is None
		assert info.env_file == ".env"
		assert info.docker is None
		assert info.health_check == HealthCheckConfig(
			kind="http",
			target="http://localhost:8000/health",
			interval_seconds=10.0,
			timeout_seconds=2.0,
			failure_threshold=5,
		)
		assert info.startup_timeout_seconds == 30.0
		assert info.nice == 5
		assert info.ionice_ioclass == "best_effort"
		assert info.ionice_value == 2

	def test_builds_a_clustered_container(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.chdir(tmp_path)
		options = StartOptions(cmd="python web.py", name="web", scale="2-4", autoscale=["cpu:80:40"])
		docker = DockerConfig(image="nginx", ports=[], volumes=[], engine="docker")

		info = _template(9, "web-1", "web", 1, options, ScaleSpec(2, 4), "python web.py", docker)

		assert info.name == "web-1"
		assert info.cluster == "web"
		assert info.cluster_index == 1
		assert info.cluster_min == 2
		assert info.cluster_max == 4
		assert info.docker == docker
		assert info.autoscale == options.autoscale_config


class TestErrorMessages:
	@pytest.mark.parametrize(
		("content", "message"),
		[
			(
				'[processes.api]\nname = "x"\ncmd = "true"\n',
				"'name' is not allowed; the table key already names the process",
			),
			('[processes.api]\ncmd = "true"\nbogus = 1\n', "unknown key 'bogus'"),
			("[processes.api]\nrestart = true\n", "'cmd' is required"),
			('[processes.api]\ncmd = ""\n', "'cmd' cannot be empty"),
			('[processes.api]\ncmd = "   "\n', "'cmd' cannot be empty"),
			('[processes.api]\ncmd = "x"\ndocker = 5\n', "'docker' must be a table"),
			('[processes.api]\ncmd = "x"\ndocker = { }\n', "'docker.image' is required"),
			('[processes.api]\ncmd = "x"\ndocker = { image = 5 }\n', "'docker.image' must be a string"),
			('[processes.api]\ncmd = "x"\ndocker = { image = "   " }\n', "'docker.image' must be a string"),
			(
				'[processes.api]\ncmd = "x"\ndocker = { image = "y", ports = "z" }\n',
				"'docker.ports' must be a list of strings",
			),
			(
				'[processes.api]\ncmd = "x"\ndocker = { image = "y", ports = [""] }\n',
				"'docker.ports' must be a list of strings",
			),
			(
				'[processes.api]\ncmd = "x"\ndocker = { image = "y", volumes = [1] }\n',
				"'docker.volumes' must be a list of strings",
			),
			('[processes.api]\ncmd = "x"\ndocker = { image = "y", engine = 5 }\n', "'docker.engine' must be a string"),
			('[processes.api]\ncmd = "x"\ndocker = { image = "y", bogus = 1 }\n', "unknown docker key 'bogus'"),
		],
	)
	def test_process_errors_cite_the_file_and_the_process(self, tmp_path: Path, content: str, message: str) -> None:
		path = write_config(tmp_path, content)

		with pytest.raises(ConfigError) as excinfo:
			load_config(path)

		assert str(excinfo.value) == f"{path}: process 'api': {message}"

	def test_unknown_root_key_cites_the_file(self, tmp_path: Path) -> None:
		path = write_config(tmp_path, 'version = 1\n[processes.api]\ncmd = "true"\n')

		with pytest.raises(ConfigError) as excinfo:
			load_config(path)

		assert str(excinfo.value) == f"{path}: unknown root key 'version'"

	def test_empty_processes_table_cites_the_file(self, tmp_path: Path) -> None:
		path = write_config(tmp_path, "[processes]\n")

		with pytest.raises(ConfigError) as excinfo:
			load_config(path)

		assert str(excinfo.value) == f"{path}: 'processes' must define at least one process"

	def test_non_table_process_cites_the_file_and_the_process(self, tmp_path: Path) -> None:
		path = write_config(tmp_path, "[processes.api]\ncmd = 5\n")

		with pytest.raises(ConfigError) as excinfo:
			load_config(path)

		assert str(excinfo.value) == f"{path}: process 'api': 'cmd' must be a string"

	def test_missing_file_cites_the_path(self, tmp_path: Path) -> None:
		path = tmp_path / "absent.toml"

		with pytest.raises(ConfigError) as excinfo:
			load_config(path)

		assert str(excinfo.value) == f"Configuration file '{path}' does not exist"

	def test_unsupported_suffix_cites_the_suffix(self, tmp_path: Path) -> None:
		path = tmp_path / "sentinel.ini"
		path.write_text("x = 1\n")

		with pytest.raises(ConfigError) as excinfo:
			load_config(path)

		assert str(excinfo.value) == "Unsupported configuration format '.ini'; use .toml, .yaml or .yml"
