"""Process management functions"""

import os
import subprocess
import time
from datetime import datetime
from typing import Protocol

import psutil

from .env import build_process_environment
from .logs import rotate_process_logs
from .state import HealthCheckConfig, ProcessInfo, State, get_log_paths


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

	if ionice_ioclass == "idle":
		pass
	elif ionice_ioclass == "best_effort":
		value = ionice_value if ionice_value is not None else 4
		if not 0 <= value <= 7:
			raise ValueError("ionice best-effort priority must be between 0 and 7")
	elif ionice_ioclass == "realtime":
		value = ionice_value if ionice_value is not None else 0
		if not 0 <= value <= 7:
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
			value = ionice_value if ionice_value is not None else 4
			ionice_fn(psutil.IOPRIO_CLASS_BE, value)
		else:
			value = ionice_value if ionice_value is not None else 0
			ionice_fn(psutil.IOPRIO_CLASS_RT, value)
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
	stdout_path, stderr_path = get_log_paths(name)
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
				if resolved_uid is not None and resolved_gid is not None:
					has_extra_groups = extra_groups is not None and len(extra_groups) > 0
					need_spawn_credentials = has_extra_groups or (
						resolved_uid != os.geteuid() or resolved_gid != os.getegid()
					)
					if need_spawn_credentials:
						if extra_groups is not None:
							proc = subprocess.Popen(
								command,
								shell=True,
								cwd=process_cwd,
								env=process_env,
								stdout=stdout_file,
								stderr=stderr_file,
								stdin=subprocess.DEVNULL,
								start_new_session=True,
								user=resolved_uid,
								group=resolved_gid,
								extra_groups=extra_groups,
							)
						else:
							proc = subprocess.Popen(
								command,
								shell=True,
								cwd=process_cwd,
								env=process_env,
								stdout=stdout_file,
								stderr=stderr_file,
								stdin=subprocess.DEVNULL,
								start_new_session=True,
								user=resolved_uid,
								group=resolved_gid,
							)
					else:
						proc = subprocess.Popen(
							command,
							shell=True,
							cwd=process_cwd,
							env=process_env,
							stdout=stdout_file,
							stderr=stderr_file,
							stdin=subprocess.DEVNULL,
							start_new_session=True,
						)
				else:
					proc = subprocess.Popen(
						command,
						shell=True,
						cwd=process_cwd,
						env=process_env,
						stdout=stdout_file,
						stderr=stderr_file,
						stdin=subprocess.DEVNULL,
						start_new_session=True,
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


def stop_process(state: State, id_or_name: int | str, force: bool = False) -> ProcessInfo:
	# Find process
	if isinstance(id_or_name, int):
		info = state.get_process(id_or_name)
	else:
		info = state.find_process_by_name(id_or_name)

	if not info:
		raise ValueError(f"Process not found: {id_or_name}")

	# Try to stop the process
	try:
		proc = psutil.Process(info.pid)
		if force:
			proc.kill()
		else:
			proc.terminate()
			try:
				proc.wait(timeout=10)
			except psutil.TimeoutExpired:
				proc.kill()
	except psutil.NoSuchProcess:
		pass

	state.remove_process(info.id)
	return info


def restart_process(state: State, id_or_name: int | str) -> ProcessInfo:
	# Find process
	if isinstance(id_or_name, int):
		info = state.get_process(id_or_name)
	else:
		info = state.find_process_by_name(id_or_name)

	if not info:
		raise ValueError(f"Process not found: {id_or_name}")

	# Store info before stopping
	cmd = info.cmd
	name = info.name
	restart = info.restart
	user = info.user
	env = info.env
	cwd = info.cwd

	# Stop the process
	stop_process(state, info.id)

	# Start new process with same settings
	return start_process(
		state,
		cmd,
		name=name,
		restart=restart,
		user=user,
		env=env,
		env_file=info.env_file,
		cwd=cwd,
		health_check=info.health_check,
		startup_timeout_seconds=info.startup_timeout_seconds,
		nice=info.nice,
		ionice_ioclass=info.ionice_ioclass,
		ionice_value=info.ionice_value,
	)


def get_process_status(info: ProcessInfo) -> dict:
	try:
		proc = psutil.Process(info.pid)
		status = proc.status()
		cpu = proc.cpu_percent()
		mem = proc.memory_info().rss
		return {
			"running": True,
			"status": status,
			"cpu_percent": cpu,
			"memory_mb": mem / (1024 * 1024),
		}
	except psutil.NoSuchProcess:
		return {
			"running": False,
			"status": "exited",
			"cpu_percent": 0,
			"memory_mb": 0,
		}


def cleanup_dead_processes(state: State) -> list[ProcessInfo]:
	dead = []
	for info in list(state.processes.values()):
		if not psutil.pid_exists(info.pid):
			state.remove_process(info.id)
			dead.append(info)
	return dead


def check_restart_needed(state: State) -> list[ProcessInfo]:
	# Check for processes that need restart and restart them
	restarted = []
	for info in list(state.processes.values()):
		if info.restart and not psutil.pid_exists(info.pid):
			try:
				new_info = start_process(
					state,
					info.cmd,
					name=info.name,
					restart=True,
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
				state.remove_process(info.id)
				restarted.append(new_info)
			except Exception:
				pass
	return restarted


def merge_process_env(group_env: dict[str, str] | None, process_env: dict[str, str] | None) -> dict[str, str]:
	"""Merge group-level and process-level environment variables. Process-level takes precedence."""
	merged: dict[str, str] = {}
	if group_env:
		merged.update(group_env)
	if process_env:
		merged.update(process_env)
	return merged


def batch_start_processes(
	state: State,
	processes: list[ProcessInfo],
) -> tuple[list[ProcessInfo], list[tuple[ProcessInfo, str]]]:
	successful: list[ProcessInfo] = []
	failed: list[tuple[ProcessInfo, str]] = []

	for info in processes:
		try:
			# Get group env if process is in a group
			group_env: dict[str, str] | None = None
			if info.group:
				group = state.get_group(info.group)
				if group:
					group_env = group.env

			# Merge environment variables (process-level takes precedence)
			merged_env = merge_process_env(group_env, info.env)

			# Start the process
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
