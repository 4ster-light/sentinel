import threading
from pathlib import Path
import pytest
from typer.testing import CliRunner
from sentinel_cli import app
from sentinel_core.process import stop_process, get_process_status
from sentinel_core.state import State, HealthCheckConfig

runner = CliRunner()


def test_regression_list_skips_probes_with_daemon(state: State, monkeypatch) -> None:
	import sentinel_cli.main as main

	monkeypatch.setattr(main, "is_daemon_running", lambda: True)

	def unexpected(*args: object, **kwargs: object) -> None:
		raise AssertionError("list must not run network probes while the daemon is running")

	monkeypatch.setattr(main, "check_and_restart_processes", unexpected)
	assert runner.invoke(app, ["list"]).exit_code == 0


def test_regression_concurrent_health_scan_and_stop(state, spawn_process, monkeypatch) -> None:
	from concurrent.futures import ThreadPoolExecutor
	import threading
	from sentinel_core.restart_monitor import check_and_restart_processes

	info = spawn_process(
		name="race", restart=True, health_check=HealthCheckConfig(kind="http", target="http://localhost")
	)
	entered = threading.Event()
	release = threading.Event()

	def probe(info) -> bool:
		entered.set()
		assert release.wait(5)
		return True

	monkeypatch.setattr("sentinel_core.restart_monitor.run_health_check", probe)
	with ThreadPoolExecutor(max_workers=2) as pool:
		scan = pool.submit(check_and_restart_processes, State(state_dir=state.store.state_dir))
		assert entered.wait(5)
		stopping = pool.submit(stop_process, State(state_dir=state.store.state_dir), info.id)
		release.set()
		scan.result(timeout=5)
		stopping.result(timeout=5)
	current = State(state_dir=state.store.state_dir)
	stopped = current.get_process(info.id)
	assert stopped is None or not get_process_status(stopped).running
	assert check_and_restart_processes(current) == ([], [])


def test_regression_stale_save_cannot_overwrite_another_writer(tmp_path: Path) -> None:
	first = State(state_dir=tmp_path / "state")
	stale = State(state_dir=first.store.state_dir)
	first.create_group("keep-me")
	with pytest.raises(ValueError, match="changed on disk"):
		stale.save()
	assert State(state_dir=first.store.state_dir).get_group("keep-me") is not None


def test_regression_concurrent_start_has_one_owner(state: State, spawn_process, monkeypatch) -> None:
	from concurrent.futures import ThreadPoolExecutor
	from sentinel_core.process import start_process
	import sentinel_core.process as process

	entered = threading.Event()
	release = threading.Event()
	original = process.subprocess.Popen

	class Gated(original):
		def __init__(self, *args, **kwargs) -> None:
			entered.set()
			assert release.wait(5)
			super().__init__(*args, **kwargs)

	monkeypatch.setattr(process.subprocess, "Popen", Gated)

	def launch(current: State) -> bool:
		try:
			start_process(current, "sleep 60", name="same")
			return True
		except ValueError:
			return False

	states = [State(state_dir=state.store.state_dir) for _ in range(2)]
	with ThreadPoolExecutor(max_workers=2) as pool:
		first = pool.submit(launch, states[0])
		assert entered.wait(5)
		second = pool.submit(launch, states[1])
		release.set()
		assert sorted([first.result(timeout=5), second.result(timeout=5)]) == [False, True]
	assert len(State(state_dir=state.store.state_dir).list_processes()) == 1
