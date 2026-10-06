import os
from datetime import datetime
from pathlib import Path

import psutil
import pytest
from typer.testing import CliRunner

from sentinel_cli import app
from sentinel_core.process import (
	ProcessIdentityError,
	cleanup_dead_processes,
	get_process_status,
	managed_process,
	restart_process,
	start_process,
	stop_process,
)
from sentinel_core.state import HealthCheckConfig, ProcessInfo, State

runner = CliRunner()


def test_regression_group_start_restores_stopped_members(state: State, spawn_process) -> None:
	from sentinel_core.process import get_process_status

	state.create_group("workers")
	info = spawn_process(name="worker")
	state.add_process_to_group("workers", info.id)
	assert runner.invoke(app, ["group", "stop", "workers"]).exit_code == 0
	assert runner.invoke(app, ["group", "start", "workers"]).exit_code == 0
	current = State().get_process(info.id)
	assert current is not None
	assert current.group == "workers"
	assert get_process_status(current).running


def test_regression_failed_group_delete_preserves_group(state: State, spawn_process, monkeypatch) -> None:
	state.create_group("workers")
	info = spawn_process(name="worker")
	state.add_process_to_group("workers", info.id)
	monkeypatch.setattr("sentinel_cli.group.batch_stop_processes", lambda *args: ([], [(info, "permission denied")]))
	result = runner.invoke(app, ["group", "delete", "workers", "--with-processes"])
	assert result.exit_code == 1
	assert State().get_group("workers") is not None
	assert "Stopped 1 process" not in result.stdout


def test_regression_stopall_then_startall(state: State, spawn_process) -> None:
	info = spawn_process(name="batch")
	assert runner.invoke(app, ["stopall"]).exit_code == 0
	assert runner.invoke(app, ["startall"]).exit_code == 0
	current = State().get_process(info.id)
	assert current is not None
	assert current.pid != info.pid
	from sentinel_core.process import get_process_status

	assert get_process_status(current).running


def test_regression_failed_startall_has_nonzero_exit(state: State, spawn_process) -> None:
	from sentinel_core.process import stop_process

	info = spawn_process(name="invalid")
	stop_process(state, info.id)
	info = state.get_process(info.id)
	assert info is not None
	info.cwd = "/nonexistent/sentinel-startall"
	state.add_process(info)
	assert runner.invoke(app, ["startall"]).exit_code == 1


def test_regression_stop_start_preserves_configuration(state, spawn_process) -> None:
	from sentinel_core.process import batch_start_processes

	state.create_group("workers")
	info = spawn_process(name="worker", restart=True)
	state.add_process_to_group("workers", info.id)
	stop_process(state, info.id)
	assert state.get_process(info.id).stopped
	started, failed = batch_start_processes(state, state.list_processes())
	assert failed == []
	assert len(started) == 1
	assert started[0].id == info.id
	assert started[0].group == "workers"
	assert started[0].pid != info.pid
	assert get_process_status(started[0]).running
	assert batch_start_processes(state, state.list_processes()) == ([], [])


def test_regression_manual_restart_preserves_id_and_group(state, spawn_process) -> None:
	state.create_group("workers")
	info = spawn_process(name="worker")
	state.add_process_to_group("workers", info.id)
	new = restart_process(state, info.id)
	assert (new.id, new.group) == (info.id, "workers")
	assert not psutil.pid_exists(info.pid)


def test_regression_failed_restart_keeps_configuration(state, spawn_process) -> None:
	info = spawn_process(name="worker")
	info.cwd = "/nonexistent/sentinel-regression"
	state.add_process(info)
	with pytest.raises(ValueError, match="Failed to start"):
		restart_process(state, info.id)
	assert state.get_process(info.id).cmd == info.cmd
	assert not get_process_status(state.get_process(info.id)).running


def test_regression_reused_pid_is_never_signalled(state, spawn_process) -> None:
	info = spawn_process(name="unrelated")
	info.create_time = psutil.Process(info.pid).create_time() - 100
	state.add_process(info)
	assert not get_process_status(info).running
	stop_process(state, info.id, force=True)
	assert psutil.Process(info.pid).is_running()


def test_regression_permission_error_keeps_process_tracked(state, spawn_process, monkeypatch) -> None:
	info = spawn_process(name="denied")

	def denied(*args: object) -> None:
		raise PermissionError("operation denied")

	with monkeypatch.context() as patch:
		patch.setattr("sentinel_core.process.os.killpg", denied)
		with pytest.raises(ValueError, match="operation denied"):
			stop_process(state, info.id, force=True)
	assert not state.get_process(info.id).stopped
	assert psutil.Process(info.pid).is_running()


def test_regression_stop_waits_for_children(state, spawn_process, tmp_path: Path, wait_for) -> None:
	import shlex
	import sys

	ready = tmp_path / "child.pid"
	code = f"import os,signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); open({str(ready)!r},'w').write(str(os.getpid())); time.sleep(60)"
	info = spawn_process(shlex.join([sys.executable, "-c", code]) + " & wait", name="parent")
	wait_for(lambda: ready.exists() and ready.read_text())
	child = psutil.Process(int(ready.read_text()))
	stop_process(state, info.id)
	assert not child.is_running() or child.status() == psutil.STATUS_ZOMBIE


def test_regression_startup_failure_stops_orphaned_children(state, tmp_path: Path, wait_for) -> None:
	pid_file = tmp_path / "child.pid"
	with pytest.raises(ValueError, match="exited during startup"):
		start_process(state, f"sleep 60 & echo $! > {pid_file}; exit 1", name="bad-start", startup_timeout_seconds=0.2)
	pid = int(pid_file.read_text())
	try:
		wait_for(lambda: not psutil.pid_exists(pid) or psutil.Process(pid).status() == psutil.STATUS_ZOMBIE)
	finally:
		if psutil.pid_exists(pid):
			psutil.Process(pid).kill()


def test_regression_state_write_failure_stops_spawned_process(state, monkeypatch) -> None:
	import subprocess

	created = []
	original = subprocess.Popen

	class Capture(original):
		def __init__(self, *args, **kwargs) -> None:
			super().__init__(*args, **kwargs)
			created.append(self)

	def fail(info: ProcessInfo) -> None:
		raise OSError("disk full")

	monkeypatch.setattr("sentinel_core.process.subprocess.Popen", Capture)
	monkeypatch.setattr(state, "add_process", fail)
	try:
		with pytest.raises(OSError, match="disk full"):
			start_process(state, "sleep 60", name="unrecorded")
		assert created[0].poll() is not None
	finally:
		for child in created:
			if child.poll() is None:
				os.killpg(child.pid, 9)
			child.wait()


def test_regression_zombie_is_not_running(state, spawn_process, wait_for) -> None:
	info = spawn_process("sleep 0.1", name="finished")
	wait_for(lambda: not psutil.pid_exists(info.pid) or psutil.Process(info.pid).status() == psutil.STATUS_ZOMBIE)
	assert not get_process_status(info).running
	assert [entry.id for entry in cleanup_dead_processes(state)] == [info.id]


def test_regression_legacy_startup_wait_preserves_process_identity(state, spawn_process) -> None:
	info = spawn_process(name="legacy", startup_timeout_seconds=1.2)
	# Older releases stored this wall-clock timestamp after the startup wait.
	info.started_at = datetime.now().isoformat()
	info.create_time = None
	state.add_process(info)
	assert get_process_status(info).running
	stop_process(state, info.id)
	assert not psutil.pid_exists(info.pid)


def test_legacy_migration_allows_extra_startup_delay(state, spawn_process) -> None:
	from sentinel_core.restart_monitor import check_and_restart_processes

	info = spawn_process(name="legacy-delay", restart=True)
	assert info.create_time is not None
	data = info.to_dict()
	data.pop("create_time")
	data.pop("base_env")
	data.pop("stopped")
	data["started_at"] = datetime.fromtimestamp(info.create_time + 30).isoformat()
	state.add_process(ProcessInfo.from_dict(data))
	assert check_and_restart_processes(state) == ([], [])
	current = State(state_dir=state.store.state_dir).get_process(info.id)
	assert current is not None
	assert current.pid == info.pid
	assert current.create_time == info.create_time
	assert get_process_status(current).running


def test_legacy_pid_created_after_record_is_not_signalled(state, spawn_process) -> None:
	info = spawn_process(name="legacy-reused")
	assert info.create_time is not None
	info.started_at = datetime.fromtimestamp(info.create_time - 60).isoformat()
	info.create_time = None
	state.add_process(info)
	with pytest.raises(ProcessIdentityError, match="Cannot verify legacy"):
		stop_process(state, info.id, force=True)
	assert psutil.Process(info.pid).is_running()
	assert not state.get_process(info.id).stopped


def test_unverified_legacy_record_is_preserved(state, spawn_process) -> None:
	from sentinel_core.restart_monitor import check_and_restart_processes

	info = spawn_process(name="legacy-unverified", restart=True)
	info.create_time = None
	info.cmd = "different command"
	state.add_process(info)
	before = state.store.state_file.read_text()
	assert get_process_status(info).status == "unknown"
	assert check_and_restart_processes(state) == ([], [])
	assert cleanup_dead_processes(state) == []
	with pytest.raises(ProcessIdentityError, match="Cannot verify legacy"):
		stop_process(state, info.id, force=True)
	assert state.store.state_file.read_text() == before
	assert psutil.Process(info.pid).is_running()


def test_legacy_migration_rejects_a_different_working_directory(state, spawn_process) -> None:
	info = spawn_process(name="legacy-cwd")
	info.create_time = None
	info.cwd = "/different-working-directory"
	with pytest.raises(ProcessIdentityError, match="Cannot verify legacy"):
		managed_process(info)


def test_legacy_zombie_does_not_trigger_an_unverified_restart(state, spawn_process, wait_for) -> None:
	from sentinel_core.restart_monitor import check_and_restart_processes

	info = spawn_process("sleep 0.1", name="legacy-zombie", restart=True)
	wait_for(lambda: psutil.Process(info.pid).status() == psutil.STATUS_ZOMBIE)
	info.create_time = None
	state.add_process(info)
	assert check_and_restart_processes(state) == ([], [])
	assert state.get_process(info.id).pid == info.pid


def test_signal_refuses_sentinels_own_process_group(monkeypatch) -> None:
	import signal
	from unittest.mock import Mock

	from sentinel_core.process import _signal_process_group

	killpg = Mock()
	monkeypatch.setattr("sentinel_core.process.os.killpg", killpg)
	with pytest.raises(ValueError, match="own process group"):
		_signal_process_group(os.getpgrp(), signal.SIGTERM)
	killpg.assert_not_called()


def test_missing_group_does_not_scan_the_process_table(monkeypatch) -> None:
	from unittest.mock import Mock

	from sentinel_core.process import _terminate_pid_if_alive

	process_iter = Mock()
	monkeypatch.setattr("sentinel_core.process.psutil.process_iter", process_iter)
	_terminate_pid_if_alive(2147483647, force=True)
	process_iter.assert_not_called()


def test_regression_health_restart_stops_old_process(state, spawn_process) -> None:
	from sentinel_core.restart_monitor import check_and_restart_processes

	state.create_group("workers")
	info = spawn_process(
		name="unhealthy",
		restart=True,
		health_check=HealthCheckConfig(kind="tcp", target="127.0.0.1:1", failure_threshold=1),
	)
	state.add_process_to_group("workers", info.id)
	restarted, _ = check_and_restart_processes(state)
	assert len(restarted) == 1
	assert not psutil.pid_exists(info.pid)
	assert restarted[0].id == info.id and restarted[0].group == "workers"
	assert len(state.list_processes()) == 1


def test_regression_stopped_process_is_not_restarted(state, spawn_process) -> None:
	from sentinel_core.restart_monitor import check_and_restart_processes

	info = spawn_process(name="paused", restart=True)
	stop_process(state, info.id)
	assert check_and_restart_processes(state) == ([], [])
	assert state.get_process(info.id).stopped


def test_regression_batch_start_keeps_group_environment(state, spawn_process, tmp_path: Path, wait_for) -> None:
	import shlex
	import sys

	from sentinel_core.process import batch_start_processes

	output = tmp_path / "group-value"
	code = f"import os,time; open({str(output)!r},'w').write(os.getenv('GROUP_VALUE','missing')); time.sleep(60)"
	state.create_group("workers", env={"GROUP_VALUE": "from-group"})
	info = spawn_process(shlex.join([sys.executable, "-c", code]), name="group-env")
	wait_for(lambda: output.exists() and output.read_text() == "missing")
	state.add_process_to_group("workers", info.id)
	stop_process(state, info.id)
	started, failed = batch_start_processes(state, state.list_processes())
	assert len(started) == 1 and failed == []
	wait_for(lambda: output.read_text() == "from-group")


def test_stop_waits_for_children_created_during_shutdown(state, spawn_process, tmp_path: Path, wait_for) -> None:
	import shlex
	import sys

	ready = tmp_path / "ready"
	child_file = tmp_path / "child.pid"
	code = f"""import signal, subprocess, time

def stop(signum, frame):
    child = subprocess.Popen(["sleep", "60"])
    open({str(child_file)!r}, "w").write(str(child.pid))
    raise SystemExit(0)

signal.signal(signal.SIGTERM, stop)
open({str(ready)!r}, "w").write("ready")
time.sleep(60)
"""
	info = spawn_process("exec " + shlex.join([sys.executable, "-c", code]), name="shutdown-parent")
	wait_for(ready.exists)
	stop_process(state, info.id)
	child_pid = int(child_file.read_text())
	assert not psutil.pid_exists(child_pid) or psutil.Process(child_pid).status() == psutil.STATUS_ZOMBIE
