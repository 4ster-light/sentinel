"""Value tests for the health probes and the docker command builders"""

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import cast

import pytest

from sentinel_core import docker, health
from sentinel_core.state import HealthCheckConfig, ProcessInfo


def health_info(**kwargs: object) -> ProcessInfo:
	return cast(ProcessInfo, SimpleNamespace(**kwargs))


def check(kind: str = "tcp", target: str = "localhost:9000", interval: float = 10.0) -> HealthCheckConfig:
	return HealthCheckConfig(
		kind=kind,
		target=target,
		interval_seconds=interval,
		timeout_seconds=2.0,
		failure_threshold=3,
	)


class TestParseHostPort:
	@pytest.mark.parametrize(
		("target", "expected"),
		[
			("localhost:9000", ("localhost", 9000)),
			(" 127.0.0.1:80 ", ("127.0.0.1", 80)),
			("[::1]:8080", ("::1", 8080)),
			("host:1", ("host", 1)),
			("host:65535", ("host", 65535)),
			("host:0", (None, None)),
			("host:65536", (None, None)),
			("host", (None, None)),
			(":9000", (None, None)),
			("host:abc", (None, None)),
			("host: 9000", ("host", 9000)),
		],
	)
	def test_parses_the_target(self, target: str, expected: tuple[str | None, int | None]) -> None:
		assert health._parse_host_port(target) == expected


class TestShouldRunHealthCheck:
	def test_without_a_check(self) -> None:
		assert health.should_run_health_check(health_info(health_check=None, health_last_checked_at=None)) is False

	def test_before_the_first_check(self) -> None:
		info = health_info(health_check=check(), health_last_checked_at=None)
		assert health.should_run_health_check(info) is True

	def test_inside_the_interval(self) -> None:
		info = health_info(health_check=check(interval=60.0), health_last_checked_at=datetime.now().isoformat())
		assert health.should_run_health_check(info) is False

	def test_after_the_interval(self) -> None:
		past = (datetime.now() - timedelta(seconds=60)).isoformat()
		info = health_info(health_check=check(interval=10.0), health_last_checked_at=past)
		assert health.should_run_health_check(info) is True

	def test_with_an_unreadable_timestamp(self) -> None:
		info = health_info(health_check=check(), health_last_checked_at="not a date")
		assert health.should_run_health_check(info) is True


class TestRunHealthCheck:
	def test_without_a_check(self) -> None:
		assert health.run_health_check(health_info(health_check=None)) is True

	def test_unknown_kind_fails(self) -> None:
		assert health.run_health_check(health_info(health_check=check(kind="icmp"))) is False

	def test_dispatches_http(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(health, "_run_http_health_check", lambda config: True)
		assert health.run_health_check(health_info(health_check=check(kind="http"))) is True

	def test_dispatches_tcp(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(health, "_run_tcp_health_check", lambda config: False)
		assert health.run_health_check(health_info(health_check=check(kind="tcp"))) is False


class TestNeedsShell:
	@pytest.mark.parametrize(
		("cmd", "expected"),
		[
			("python app.py", False),
			("sleep 60", False),
			("python app.py && echo done", True),
			("python a.py; python b.py", True),
			("python a.py\npython b.py", True),
			("MODE=prod python app.py", True),
			("echo 'a && b'", False),
			('python -c "print(1)"', False),
			("echo 'unterminated", True),
			("", False),
		],
	)
	def test_detects_compound_commands(self, cmd: str, expected: bool) -> None:
		assert docker._needs_shell(cmd) is expected


class TestDockerCommands:
	def test_container_name(self) -> None:
		assert docker.container_name("web-1") == "sentinel-web-1"

	def test_simple_command_uses_exec(self) -> None:
		line = docker.build_run_line("docker", "web", "nginx:alpine", "python app.py")
		assert line == "docker run --rm --name sentinel-web nginx:alpine sh -c 'exec python app.py'"

	def test_compound_command_keeps_the_shell(self) -> None:
		line = docker.build_run_line("podman", "job", "alpine", "echo a && echo b")
		assert line == "podman run --rm --name sentinel-job alpine sh -c 'echo a && echo b'"

	def test_ports_and_volumes_come_before_the_image(self) -> None:
		line = docker.build_run_line(
			"docker",
			"web",
			"nginx",
			"sleep 60",
			ports=["8080:80", "443:443"],
			volumes=["data:/data"],
		)
		assert line == (
			"docker run --rm --name sentinel-web -p 8080:80 -p 443:443 -v data:/data nginx sh -c 'exec sleep 60'"
		)

	def test_stop_command(self) -> None:
		assert docker.build_stop_command("docker", "web") == ["docker", "stop", "-t", "10", "sentinel-web"]
		assert docker.build_stop_command("docker", "web", force=True) == ["docker", "kill", "sentinel-web"]

	def test_explicit_engine(self) -> None:
		assert docker.resolve_engine("podman") == "podman"
		with pytest.raises(ValueError, match="unknown container engine"):
			docker.resolve_engine("containerd")

	def test_path_discovery(self, monkeypatch: pytest.MonkeyPatch) -> None:
		found = {"podman": "/usr/bin/podman"}
		monkeypatch.setattr(docker.shutil, "which", lambda name: found.get(name))
		assert docker.resolve_engine() == "podman"

	def test_no_engine_on_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(docker.shutil, "which", lambda name: None)
		with pytest.raises(ValueError, match="no container engine"):
			docker.resolve_engine()
