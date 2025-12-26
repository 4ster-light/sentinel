"""Process management functions"""

import os
import subprocess
from datetime import datetime

import psutil

from .state import ProcessInfo, State, get_log_paths


def start_process(
	state: State,
	cmd: str,
	name: str | None = None,
	restart: bool = False,
	env: dict[str, str] | None = None,
) -> ProcessInfo:
	"""Start a new background process"""
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

	# Merge current environment with provided env
	process_env = os.environ.copy()
	if env:
		process_env.update(env)

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
	)

	state.add_process(info)
	return info


def stop_process(state: State, id_or_name: int | str, force: bool = False) -> ProcessInfo:
	"""Stop a running process"""
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
	"""Restart a process"""
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
	"""Get the status of a process"""
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
	"""Remove processes that are no longer running"""
	dead = []
	for info in list(state.processes.values()):
		if not psutil.pid_exists(info.pid):
			state.remove_process(info.id)
			dead.append(info)
	return dead


def check_restart_needed(state: State) -> list[ProcessInfo]:
	"""Check for processes that need restart and restart them"""
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
