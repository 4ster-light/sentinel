"""Process management functions"""

import os
import shlex
import signal
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, cast

import psutil

from .env import build_process_environment
from .logs import rotate_process_logs
from .state import HealthCheckConfig, ProcessInfo, ProcessStatus, State, get_log_paths, serialized


class _SpawnedChild(Protocol):
	pid: int

	def poll(self) -> int | None: ...


class ProcessIdentityError(ValueError):
	pass


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


def managed_process(info: ProcessInfo, include_zombie: bool = False) -> psutil.Process | None:
	if info.stopped or info.pid <= 0:
		return None
	try:
		proc = psutil.Process(info.pid)
		created = proc.create_time()
		if info.create_time is not None:
			if created != info.create_time:
				return None
		else:
			try:
				started = datetime.fromisoformat(info.started_at).timestamp()
				arguments = shlex.split(info.cmd)
			except ValueError as e:
				raise ProcessIdentityError(f"Cannot verify legacy process '{info.name}'") from e
			if arguments and arguments[0] == "exec":
				arguments = arguments[1:]
			try:
				actual_arguments = proc.cmdline()
			except psutil.ZombieProcess as e:
				raise ProcessIdentityError(f"Cannot verify legacy process '{info.name}'") from e
			# Old timestamps were recorded after startup; creation may be much earlier.
			clock_tick = 1 / os.sysconf("SC_CLK_TCK")
			if (
				created > started + clock_tick
				or actual_arguments not in (["/bin/sh", "-c", info.cmd], arguments)
				or proc.cwd() != info.cwd
				or os.getpgid(info.pid) != info.pid
			):
				raise ProcessIdentityError(f"Cannot verify legacy process '{info.name}'; its state was left unchanged")
			info.create_time = created
		return proc if include_zombie or proc.status() != psutil.STATUS_ZOMBIE else None
	except psutil.NoSuchProcess, ProcessLookupError:
		return None


def _terminate_pid_if_alive(pid: int, force: bool = False) -> None:
	_signal_process_group(pid, signal.SIGKILL if force else signal.SIGTERM)
	deadline = time.monotonic() + (2 if force else 10)
	empty_scan = False

	while True:
		try:
			os.killpg(pid, 0)
		except ProcessLookupError:
			return
		alive = False
		# A signal handler can fork after SIGTERM, so rescan the whole group.
		for proc in psutil.process_iter():
			try:
				if os.getpgid(proc.pid) != pid:
					continue
				if proc.status() == psutil.STATUS_ZOMBIE:
					proc.wait(timeout=0)
				else:
					alive = True
			except ProcessLookupError, psutil.NoSuchProcess, psutil.TimeoutExpired:
				continue

		# Confirm an empty scan: a parent may have exited after the PID snapshot.
		if not alive and empty_scan:
			return
		empty_scan = not alive
		if alive and time.monotonic() >= deadline:
			if force:
				raise ValueError(f"Process group {pid} did not stop")
			_signal_process_group(pid, signal.SIGKILL)
			force = True
			deadline = time.monotonic() + 2
		time.sleep(0.1)


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


@serialized
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
	group: str | None = None,
	process_id: int | None = None,
	base_env: dict[str, str] | None = None,
) -> ProcessInfo:
	command = cmd.strip()
	if not command:
		raise ValueError("Command cannot be empty")

	process_cwd = str(Path(cwd or os.getcwd()).resolve())
	env_file = str(Path(env_file).resolve()) if env_file else None
	group_info = state.get_group(group) if group else None
	if group and group_info is None:
		raise ValueError(f"Group '{group}' does not exist")

	# Generate name from command if not provided
	if name is None:
		name = command.split()[0].split("/")[-1]

	# Check for duplicate names
	existing = state.find_process_by_name(name)
	if existing and (existing.id != process_id or not existing.stopped):
		raise ValueError(f"Process with name '{name}' already exists (id: {existing.id})")

	# Setup log files
	stdout_path, stderr_path = get_log_paths(name, logs_dir=state.logs_dir)
	rotate_process_logs(str(stdout_path), str(stderr_path))
	stdout_path.touch(mode=0o600, exist_ok=True)
	stderr_path.touch(mode=0o600, exist_ok=True)

	resolved_username: str | None = None
	resolved_uid: int | None = None
	resolved_gid: int | None = None
	resolved_group_ids: list[int] | None = None
	if user is not None:
		resolved_username, resolved_uid, resolved_gid, resolved_group_ids = _resolve_process_user(user)
		_validate_user_permissions(resolved_username, resolved_uid, resolved_gid)

	# Capture inherited values once; restarts must not inherit the daemon's environment.
	if base_env is None:
		base_env = build_process_environment()
		if resolved_uid is not None:
			import pwd

			account = pwd.getpwuid(resolved_uid)
			base_env.update(HOME=account.pw_dir, USER=account.pw_name, LOGNAME=account.pw_name, SHELL=account.pw_shell)
	process_env = base_env | build_process_environment(
		system_env=False,
		global_env_files=False,
		group_env=group_info.env if group_info else None,
		group_env_file=group_info.env_file if group_info else None,
		process_env=env,
		process_env_file=env_file,
	)

	extra_groups = _build_extra_groups(resolved_gid, resolved_group_ids)

	started_at = datetime.now().isoformat()
	create_time: float | None = None
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
			create_time = psutil.Process(pid).create_time()
		except psutil.NoSuchProcess:
			pass

		prio_warnings = _apply_process_priority(pid, nice, ionice_ioclass, ionice_value)
		if priority_warnings is not None:
			priority_warnings.extend(prio_warnings)

		if startup_timeout_seconds is not None and startup_timeout_seconds > 0:
			_wait_startup_or_fail(proc, startup_timeout_seconds)
		info = ProcessInfo(
			id=process_id if process_id is not None else state.get_next_id(),
			pid=proc.pid,
			name=name,
			cmd=command,
			cwd=process_cwd,
			restart=restart,
			user=resolved_username,
			started_at=started_at,
			create_time=create_time,
			base_env=base_env,
			group=group,
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
	except BaseException:
		if proc is not None:
			_terminate_pid_if_alive(proc.pid, force=True)
		raise


def _signal_process_group(pid: int, sig: int) -> None:
	if pid == os.getpgrp():
		raise ValueError("Refusing to signal Sentinel's own process group")
	try:
		os.killpg(pid, sig)
	except ProcessLookupError:
		pass


@serialized
def stop_process(state: State, id_or_name: int | str, force: bool = False) -> ProcessInfo:
	info = state.find_process(id_or_name)
	if not info:
		raise ValueError(f"Process not found: {id_or_name}")
	try:
		if (
			not info.stopped
			and info.pid > 0
			and (managed_process(info, include_zombie=True) is not None or not psutil.pid_exists(info.pid))
		):
			_terminate_pid_if_alive(info.pid, force=force)
	except (OSError, psutil.Error) as e:
		raise ValueError(f"Failed to stop process '{info.name}': {e}") from e
	info.stopped = True
	state.add_process(info)
	return info


def restart_from_info(state: State, info: ProcessInfo) -> ProcessInfo:
	return start_process(
		state,
		info.cmd,
		name=info.name,
		process_id=info.id,
		base_env=info.base_env,
		group=info.group,
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


@serialized
def restart_process(state: State, id_or_name: int | str) -> ProcessInfo:
	info = state.find_process(id_or_name)

	if not info:
		raise ValueError(f"Process not found: {id_or_name}")

	old_id = info.id
	stop_process(state, old_id)
	return restart_from_info(state, info)


def get_process_status(info: ProcessInfo) -> ProcessStatus:
	try:
		proc = managed_process(info)
		if proc is None:
			return ProcessStatus(False, "stopped" if info.stopped else "exited", 0, 0)
		status = proc.status()
		processes = [proc, *proc.children(recursive=True)]
		for member in processes:
			try:
				member.cpu_percent()
			except psutil.NoSuchProcess:
				pass
		# psutil needs two samples; sample the shell and its children together.
		time.sleep(0.1)
		cpu = 0.0
		mem = 0
		for member in processes:
			try:
				cpu += member.cpu_percent()
				mem += member.memory_info().rss
			except psutil.NoSuchProcess, psutil.AccessDenied:
				continue
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

	except psutil.AccessDenied, ProcessIdentityError:
		return ProcessStatus(running=False, status="unknown", cpu_percent=0, memory_mb=0)


@serialized
def cleanup_dead_processes(state: State) -> list[ProcessInfo]:
	dead = []
	for info in list(state.processes.values()):
		legacy = info.create_time is None
		try:
			proc = managed_process(info)
		except ProcessIdentityError:
			continue
		if proc is None:
			state.remove_process(info.id)
			dead.append(info)
		elif legacy:
			state.add_process(info)
	return dead


@serialized
def batch_start_processes(
	state: State,
	processes: list[ProcessInfo],
) -> tuple[list[ProcessInfo], list[tuple[ProcessInfo, str]]]:
	successful: list[ProcessInfo] = []
	failed: list[tuple[ProcessInfo, str]] = []

	for info in processes:
		try:
			info = state.get_process(info.id) or info
			if managed_process(info) is not None:
				continue
			if state.get_process(info.id):
				stop_process(state, info.id)
			new_info = restart_from_info(state, info)
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
