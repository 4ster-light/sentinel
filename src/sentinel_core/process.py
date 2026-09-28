"""Process management functions"""

import os
import signal
import subprocess
import time
from datetime import datetime
from typing import Any, Protocol, cast

import psutil

from .env import build_process_environment, merge_environments
from .logs import rotate_process_logs
from .state import HealthCheckConfig, ProcessInfo, ProcessStatus, State, get_log_paths


class _SpawnedChild(Protocol):
	pid: int

	def poll(self) -> int | None: ...


def _resolve_process_user(user: str) -> tuple[str, int, int, list[int]]:
	if os.name == "nt":
		raise ValueError("Running a process as a specific user is not supported on Windows")

	user_spec = user.strip()
	if not user_spec:
		raise ValueError("Process user cannot be empty")

	import pwd

	if user_spec.isdigit():
		uid = int(user_spec)
		try:
			entry = pwd.getpwuid(uid)
		except KeyError as e:
			raise ValueError(f"User with UID {uid} was not found") from e
		return entry.pw_name, entry.pw_uid, entry.pw_gid, os.getgrouplist(entry.pw_name, entry.pw_gid)

	try:
		entry = pwd.getpwnam(user_spec)
	except KeyError as e:
		raise ValueError(f"User '{user_spec}' was not found") from e
	return entry.pw_name, entry.pw_uid, entry.pw_gid, os.getgrouplist(entry.pw_name, entry.pw_gid)


def _validate_user_permissions(username: str, uid: int, gid: int) -> None:
	if os.name == "nt":
		raise ValueError("Running a process as a specific user is not supported on Windows")

	current_uid = os.geteuid()
	current_gid = os.getegid()

	if current_uid == 0:
		return

	if uid != current_uid:
		raise ValueError(
			f"Cannot run as user '{username}' (uid: {uid}) without root privileges; current uid is {current_uid}"
		)

	if gid != current_gid:
		raise ValueError(
			f"Cannot switch to primary gid {gid} for user '{username}' without root privileges; current gid is {current_gid}"
		)


def _build_extra_groups(gid: int | None, group_ids: list[int] | None) -> list[int] | None:
	if os.name == "nt" or gid is None or group_ids is None:
		return None

	if os.geteuid() != 0:
		return None

	return [group_id for group_id in group_ids if group_id != gid]


def _terminate_pid_if_alive(pid: int) -> None:
	try:
		proc = psutil.Process(pid)
		proc.terminate()
		try:
			proc.wait(timeout=5)
		except psutil.TimeoutExpired:
			proc.kill()
	except psutil.NoSuchProcess:
		pass


def _apply_process_priority(
	pid: int,
	nice: int | None,
	ionice_ioclass: str | None,
	ionice_value: int | None,
) -> list[str]:
	warnings: list[str] = []
	proc = psutil.Process(pid)
	if nice is not None:
		try:
			proc.nice(nice)
		except (psutil.Error, PermissionError, OSError, AttributeError) as e:
			warnings.append(f"Could not set CPU priority (nice={nice}): {e}. Using default CPU priority.")

	if ionice_ioclass is None:
		return warnings

	resolved_value: int | None = None
	if ionice_ioclass == "idle":
		pass
	elif ionice_ioclass == "best_effort":
		resolved_value = ionice_value if ionice_value is not None else 4
		if not 0 <= resolved_value <= 7:
			raise ValueError("ionice best-effort priority must be between 0 and 7")
	elif ionice_ioclass == "realtime":
		resolved_value = ionice_value if ionice_value is not None else 0
		if not 0 <= resolved_value <= 7:
			raise ValueError("ionice realtime priority must be between 0 and 7")
	else:
		raise ValueError(f"unknown ionice class: {ionice_ioclass}")

	if not hasattr(psutil, "IOPRIO_CLASS_IDLE"):
		warnings.append("I/O scheduling class (ionice) is not available on this platform; ionice was skipped.")
		return warnings

	ionice_fn = getattr(proc, "ionice", None)
	if ionice_fn is None:
		warnings.append("I/O scheduling class (ionice) is not available on this platform; ionice was skipped.")
		return warnings

	try:
		if ionice_ioclass == "idle":
			ionice_fn(psutil.IOPRIO_CLASS_IDLE)
		elif ionice_ioclass == "best_effort":
			ionice_fn(psutil.IOPRIO_CLASS_BE, resolved_value)
		else:
			ionice_fn(psutil.IOPRIO_CLASS_RT, resolved_value)
	except (psutil.Error, PermissionError, OSError, ValueError) as e:
		warnings.append(f"Could not apply ionice ({ionice_ioclass}): {e}. Using default I/O scheduling.")

	return warnings


def _wait_startup_or_fail(proc: _SpawnedChild, startup_timeout_seconds: float) -> None:
	deadline = time.monotonic() + startup_timeout_seconds
	while True:
		code = proc.poll()
		if code is not None:
			raise ValueError(f"Process exited during startup timeout (exit code: {code})")
		if time.monotonic() >= deadline:
			return
		time.sleep(0.05)


def start_process(
	state: State,
	cmd: str,
	name: str | None = None,
	restart: bool = False,
	user: str | None = None,
	env: dict[str, str] | None = None,
	env_file: str | None = None,
	cwd: str | None = None,
	health_check: HealthCheckConfig | None = None,
	startup_timeout_seconds: float | None = None,
	nice: int | None = None,
	ionice_ioclass: str | None = None,
	ionice_value: int | None = None,
	priority_warnings: list[str] | None = None,
) -> ProcessInfo:
	command = cmd.strip()
	if not command:
		raise ValueError("Command cannot be empty")

	process_cwd = cwd or os.getcwd()

	# Generate name from command if not provided
	if name is None:
		name = command.split()[0].split("/")[-1]

	# Check for duplicate names
	existing = state.find_process_by_name(name)
	if existing:
		raise ValueError(f"Process with name '{name}' already exists (id: {existing.id})")

	# Setup log files
	stdout_path, stderr_path = get_log_paths(name, logs_dir=state.logs_dir)
	rotate_process_logs(str(stdout_path), str(stderr_path))

	# Build merged environment with proper precedence
	process_env = build_process_environment(
		system_env=True,
		global_env_files=True,
		process_env=env,
		process_env_file=env_file,
	)

	resolved_username: str | None = None
	resolved_uid: int | None = None
	resolved_gid: int | None = None
	resolved_group_ids: list[int] | None = None
	if user is not None:
		resolved_username, resolved_uid, resolved_gid, resolved_group_ids = _resolve_process_user(user)
		_validate_user_permissions(resolved_username, resolved_uid, resolved_gid)

	extra_groups = _build_extra_groups(resolved_gid, resolved_group_ids)

	proc: subprocess.Popen[bytes] | None = None
	try:
		with open(stdout_path, "a") as stdout_file, open(stderr_path, "a") as stderr_file:
			try:
				popen_kwargs: dict[str, Any] = {}
				if resolved_uid is not None and resolved_gid is not None:
					has_extra_groups = extra_groups is not None and len(extra_groups) > 0
					need_spawn_credentials = has_extra_groups or (
						resolved_uid != os.geteuid() or resolved_gid != os.getegid()
					)
					if need_spawn_credentials:
						popen_kwargs["user"] = resolved_uid
						popen_kwargs["group"] = resolved_gid
						if extra_groups is not None:
							popen_kwargs["extra_groups"] = extra_groups

				proc = cast(
					subprocess.Popen[bytes],
					subprocess.Popen(
						command,
						shell=True,
						cwd=process_cwd,
						env=process_env,
						stdout=stdout_file,
						stderr=stderr_file,
						stdin=subprocess.DEVNULL,
						start_new_session=True,
						**popen_kwargs,
					),
				)
			except (OSError, subprocess.SubprocessError) as e:
				raise ValueError(f"Failed to start process '{name}': {e}") from e

		assert proc is not None
		pid = proc.pid

		try:
			prio_warnings = _apply_process_priority(pid, nice, ionice_ioclass, ionice_value)
		except ValueError:
			_terminate_pid_if_alive(pid)
			raise
		if priority_warnings is not None:
			priority_warnings.extend(prio_warnings)

		if startup_timeout_seconds is not None and startup_timeout_seconds > 0:
			try:
				_wait_startup_or_fail(proc, startup_timeout_seconds)
			except ValueError:
				_terminate_pid_if_alive(pid)
				raise
	except BaseException:
		if proc is not None and proc.poll() is None:
			_terminate_pid_if_alive(proc.pid)
		raise

	assert proc is not None
	info = ProcessInfo(
		id=state.get_next_id(),
		pid=proc.pid,
		name=name,
		cmd=command,
		cwd=process_cwd,
		restart=restart,
		user=resolved_username,
		started_at=datetime.now().isoformat(),
		stdout_log=str(stdout_path),
		stderr_log=str(stderr_path),
		env=env or {},
		env_file=env_file,
		health_check=health_check,
		startup_timeout_seconds=startup_timeout_seconds,
		nice=nice,
		ionice_ioclass=ionice_ioclass,
		ionice_value=ionice_value,
	)

	state.add_process(info)
	return info


def _signal_pid(pid: int, sig: int) -> None:
	try:
		os.kill(pid, sig)
	except OSError:
		pass


def _signal_process_group(pid: int, sig: int) -> None:
	"""Signal the process group led by pid so shell children die with it.

	Falls back to signaling the leader alone when group signaling is unavailable,
	and never signals the group the caller itself runs in.
	"""
	getpgid = getattr(os, "getpgid", None)
	killpg = getattr(os, "killpg", None)
	if getpgid is None or killpg is None:
		_signal_pid(pid, sig)
		return

	try:
		pgid = getpgid(pid)
	except OSError:
		return

	if pgid == getpgid(0):
		_signal_pid(pid, sig)
		return

	try:
		killpg(pgid, sig)
	except OSError:
		_signal_pid(pid, sig)


def stop_process(state: State, id_or_name: int | str, force: bool = False) -> ProcessInfo:
	info = state.find_process(id_or_name)

	if not info:
		raise ValueError(f"Process not found: {id_or_name}")

	# Stop the process (and its whole process group, since processes are
	# started with start_new_session=True)
	try:
		proc = psutil.Process(info.pid)
	except psutil.NoSuchProcess:
		pass
	else:
		if force:
			_signal_process_group(info.pid, signal.SIGKILL)
		else:
			_signal_process_group(info.pid, signal.SIGTERM)
			try:
				proc.wait(timeout=10)
			except psutil.TimeoutExpired:
				_signal_process_group(info.pid, signal.SIGKILL)

	state.remove_process(info.id)
	return info


def restart_from_info(state: State, info: ProcessInfo) -> ProcessInfo:
	return start_process(
		state,
		info.cmd,
		name=info.name,
		restart=info.restart,
		user=info.user,
		env=info.env,
		env_file=info.env_file,
		cwd=info.cwd,
		health_check=info.health_check,
		startup_timeout_seconds=info.startup_timeout_seconds,
		nice=info.nice,
		ionice_ioclass=info.ionice_ioclass,
		ionice_value=info.ionice_value,
	)


def restart_process(state: State, id_or_name: int | str) -> ProcessInfo:
	info = state.find_process(id_or_name)

	if not info:
		raise ValueError(f"Process not found: {id_or_name}")

	old_id = info.id
	stop_process(state, old_id)
	return restart_from_info(state, info)


def get_process_status(info: ProcessInfo) -> ProcessStatus:
	try:
		proc = psutil.Process(info.pid)
		status = proc.status()
		cpu = proc.cpu_percent()
		mem = proc.memory_info().rss
		return ProcessStatus(
			running=True,
			status=status,
			cpu_percent=cpu,
			memory_mb=mem / (1024 * 1024),
		)
	except psutil.NoSuchProcess:
		return ProcessStatus(
			running=False,
			status="exited",
			cpu_percent=0,
			memory_mb=0,
		)


def cleanup_dead_processes(state: State) -> list[ProcessInfo]:
	dead = []
	for info in list(state.processes.values()):
		if not psutil.pid_exists(info.pid):
			state.remove_process(info.id)
			dead.append(info)
	return dead


def batch_start_processes(
	state: State,
	processes: list[ProcessInfo],
) -> tuple[list[ProcessInfo], list[tuple[ProcessInfo, str]]]:
	successful: list[ProcessInfo] = []
	failed: list[tuple[ProcessInfo, str]] = []

	for info in processes:
		try:
			group_env: dict[str, str] | None = None
			if info.group:
				group = state.get_group(info.group)
				if group:
					group_env = group.env

			merged_env = merge_environments(group_env, info.env)

			new_info = start_process(
				state,
				info.cmd,
				name=info.name,
				restart=info.restart,
				user=info.user,
				env=merged_env if merged_env else None,
				env_file=info.env_file,
				cwd=info.cwd,
				health_check=info.health_check,
				startup_timeout_seconds=info.startup_timeout_seconds,
				nice=info.nice,
				ionice_ioclass=info.ionice_ioclass,
				ionice_value=info.ionice_value,
			)
			successful.append(new_info)
		except Exception as e:
			failed.append((info, str(e)))

	return successful, failed


def batch_stop_processes(
	state: State,
	processes: list[ProcessInfo],
	force: bool = False,
) -> tuple[list[ProcessInfo], list[tuple[ProcessInfo, str]]]:
	successful: list[ProcessInfo] = []
	failed: list[tuple[ProcessInfo, str]] = []

	for info in processes:
		try:
			stopped_info = stop_process(state, info.id, force=force)
			successful.append(stopped_info)
		except Exception as e:
			failed.append((info, str(e)))

	return successful, failed


def batch_restart_processes(
	state: State,
	processes: list[ProcessInfo],
) -> tuple[list[ProcessInfo], list[tuple[ProcessInfo, str]]]:
	successful: list[ProcessInfo] = []
	failed: list[tuple[ProcessInfo, str]] = []

	for info in processes:
		try:
			restarted_info = restart_process(state, info.id)
			successful.append(restarted_info)
		except Exception as e:
			failed.append((info, str(e)))

	return successful, failed
