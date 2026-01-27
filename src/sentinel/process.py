"""Process management functions"""

import os
import subprocess
from datetime import datetime

import psutil

from .env import build_process_environment
from .state import ProcessInfo, State, get_log_paths


def start_process(
	state: State,
	cmd: str,
	name: str | None = None,
	restart: bool = False,
	env: dict[str, str] | None = None,
	env_file: str | None = None,
) -> ProcessInfo:
	cwd = os.getcwd()

	# Generate name from command if not provided
	if name is None:
		name = cmd.split()[0].split("/")[-1]

	# Check for duplicate names
	existing = state.find_process_by_name(name)
	if existing:
		raise ValueError(f"Process with name '{name}' already exists (id: {existing.id})")

	# Setup log files
	stdout_path, stderr_path = get_log_paths(name)

	# Build merged environment with proper precedence
	process_env = build_process_environment(
		system_env=True,
		global_env_files=True,
		process_env=env,
		process_env_file=env_file,
	)

	# Open log files
	stdout_file = open(stdout_path, "a")
	stderr_file = open(stderr_path, "a")

	# Start the process
	proc = subprocess.Popen(
		cmd,
		shell=True,
		cwd=cwd,
		env=process_env,
		stdout=stdout_file,
		stderr=stderr_file,
		stdin=subprocess.DEVNULL,
		start_new_session=True,
	)

	# Close file handles in parent process
	stdout_file.close()
	stderr_file.close()

	# Create process info
	info = ProcessInfo(
		id=state.get_next_id(),
		pid=proc.pid,
		name=name,
		cmd=cmd,
		cwd=cwd,
		restart=restart,
		started_at=datetime.now().isoformat(),
		stdout_log=str(stdout_path),
		stderr_log=str(stderr_path),
		env=env or {},
		env_file=env_file,
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
	env = info.env
	cwd = info.cwd

	# Stop the process
	stop_process(state, info.id)

	# Start new process with same settings
	os.chdir(cwd)
	return start_process(state, cmd, name, restart, env)


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
				os.chdir(info.cwd)
				new_info = start_process(
					state,
					info.cmd,
					name=info.name,
					restart=True,
					env=info.env,
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
			os.chdir(info.cwd)
			new_info = start_process(
				state,
				info.cmd,
				name=info.name,
				restart=info.restart,
				env=merged_env if merged_env else None,
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
