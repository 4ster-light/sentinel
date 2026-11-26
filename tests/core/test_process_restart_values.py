"""Value tests for the restart and container stop helpers"""

from types import SimpleNamespace
from typing import cast

import pytest

import sentinel_core.process as process
from sentinel_core.models import AutoscaleConfig, DockerConfig, HealthCheckConfig, ProcessInfo
from sentinel_core.state import State


class FastClock:
	def __init__(self) -> None:
		self.now = 0.0

	def monotonic(self) -> float:
		return self.now

	def sleep(self, seconds: float) -> None:
		self.now += 1.0


def record() -> ProcessInfo:
	return ProcessInfo(
		id=7,
		pid=4242,
		name="api",
		cmd="python app.py",
		cwd="/srv/app",
		restart=True,
		started_at="",
		stdout_log="",
		stderr_log="",
		base_env={"A": "1"},
		group="staff",
		depends_on=["db"],
		cluster="web",
		cluster_index=2,
		cluster_min=2,
		cluster_max=4,
		autoscale=AutoscaleConfig(cpu_high=80.0, cpu_low=40.0),
		user="alice",
		env={"B": "2"},
		env_file=".env",
		health_check=HealthCheckConfig(
			kind="tcp", target="localhost:9000", interval_seconds=10.0, timeout_seconds=2.0, failure_threshold=3
		),
		startup_timeout_seconds=30.0,
		nice=5,
		ionice_ioclass="best_effort",
		ionice_value=2,
		docker=DockerConfig(image="nginx", ports=["8080:80"], volumes=[], engine="podman"),
	)


def container(engine: str | None = "podman") -> ProcessInfo:
	info = record()
	info.docker = DockerConfig(image="nginx", ports=[], volumes=[], engine=engine)
	return info


class TestRestartFromInfo:
	def test_passes_every_recorded_field(self, monkeypatch: pytest.MonkeyPatch) -> None:
		calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
		sentinel = record()
		monkeypatch.setattr(
			process,
			"start_process",
			lambda *args, **kwargs: calls.append((args, kwargs)) or sentinel,
		)
		state = cast(State, SimpleNamespace())

		assert process.restart_from_info(state, record()) is sentinel

		args, kwargs = calls[0]
		assert args == (state, "python app.py")
		assert kwargs == {
			"name": "api",
			"process_id": 7,
			"base_env": {"A": "1"},
			"group": "staff",
			"depends_on": ["db"],
			"cluster": "web",
			"cluster_index": 2,
			"cluster_min": 2,
			"cluster_max": 4,
			"autoscale": record().autoscale,
			"restart": True,
			"user": "alice",
			"env": {"B": "2"},
			"env_file": ".env",
			"cwd": "/srv/app",
			"health_check": record().health_check,
			"startup_timeout_seconds": 30.0,
			"nice": 5,
			"ionice_ioclass": "best_effort",
			"ionice_value": 2,
			"docker": record().docker,
		}


class TestStopContainer:
	@pytest.fixture(autouse=True)
	def bounded_stop(self, monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, bool]]:
		monkeypatch.setattr(process, "time", FastClock())
		terminated: list[tuple[int, bool]] = []
		monkeypatch.setattr(
			process, "_terminate_pid_if_alive", lambda pid, force=False: terminated.append((pid, force))
		)
		return terminated

	def test_stops_with_the_recorded_engine(self, monkeypatch: pytest.MonkeyPatch) -> None:
		runs: list[tuple[tuple[object, ...], dict[str, object]]] = []
		monkeypatch.setattr(process.subprocess, "run", lambda *args, **kwargs: runs.append((args, kwargs)))
		monkeypatch.setattr(process, "managed_process", lambda target: None)

		process._stop_container(container())

		args, kwargs = runs[0]
		assert args[0] == ["podman", "stop", "-t", "10", "sentinel-api"]
		assert kwargs == {"capture_output": True, "check": False, "timeout": process.STOP_GRACE_SECONDS + 5}

	def test_resolves_the_engine_when_it_is_not_recorded(self, monkeypatch: pytest.MonkeyPatch) -> None:
		runs: list[tuple[tuple[object, ...], dict[str, object]]] = []
		monkeypatch.setattr(process.subprocess, "run", lambda *args, **kwargs: runs.append((args, kwargs)))
		monkeypatch.setattr(process, "resolve_engine", lambda explicit: "docker")
		monkeypatch.setattr(process, "managed_process", lambda target: None)

		process._stop_container(container(engine=None))

		assert runs[0][0][0] == ["docker", "stop", "-t", "10", "sentinel-api"]

	def test_skips_the_engine_when_none_is_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
		runs: list[tuple[tuple[object, ...], dict[str, object]]] = []
		monkeypatch.setattr(process.subprocess, "run", lambda *args, **kwargs: runs.append((args, kwargs)))
		monkeypatch.setattr(process, "resolve_engine", lambda explicit: (_ for _ in ()).throw(ValueError("none")))
		monkeypatch.setattr(process, "managed_process", lambda target: None)

		process._stop_container(container(engine=None))

		assert runs == []

	def test_ignores_an_engine_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
		def failing(*args: object, **kwargs: object) -> None:
			raise OSError("engine gone")

		monkeypatch.setattr(process.subprocess, "run", failing)
		monkeypatch.setattr(process, "managed_process", lambda target: None)

		process._stop_container(container())

	def test_kills_the_wrapper_that_survives_the_engine(
		self, monkeypatch: pytest.MonkeyPatch, bounded_stop: list[tuple[int, bool]]
	) -> None:
		monkeypatch.setattr(process.subprocess, "run", lambda *args, **kwargs: None)
		monkeypatch.setattr(process, "managed_process", lambda target: object())

		process._stop_container(container())

		assert bounded_stop == [(4242, True)]

	def test_force_uses_the_kill_command(self, monkeypatch: pytest.MonkeyPatch) -> None:
		runs: list[tuple[tuple[object, ...], dict[str, object]]] = []
		monkeypatch.setattr(process.subprocess, "run", lambda *args, **kwargs: runs.append((args, kwargs)))
		monkeypatch.setattr(process, "managed_process", lambda target: None)

		process._stop_container(container(), force=True)

		assert runs[0][0][0] == ["podman", "kill", "sentinel-api"]
