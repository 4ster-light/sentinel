"""Daemon commands for continuous process monitoring"""

import logging
import os
import signal
import subprocess
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

import psutil
import typer
from rich.console import Console

from sentinel_core.logs import DEFAULT_LOG_ROTATION_BACKUPS, DEFAULT_LOG_ROTATION_MAX_BYTES
from sentinel_core.restart_monitor import RestartMonitor
from sentinel_core.state import ProcessInfo
from sentinel_core.state import STATE_DIR

console = Console()
daemon_app = typer.Typer(name="daemon", help="Manage the restart monitor daemon", no_args_is_help=True)

logger = logging.getLogger(__name__)

DAEMON_PID_FILE: Path = STATE_DIR / "daemon.pid"

DAEMON_RUN_ARG = "monitor"


def _daemon_subprocess_env() -> dict[str, str]:
	"""Environment for the spawned daemon, carrying module search visibility.

	Distributions such as Nix wrap the console script and add their store
	site directories to sys.path at startup, so a bare
	`python -m sentinel_cli.daemon` child cannot import the package or its
	dependencies. Propagating the current interpreter's importable path
	entries keeps the daemon importable.
	"""
	env = {**os.environ, "SENTINEL_STATE_DIR": str(STATE_DIR)}
	extra_paths = [p for p in sys.path if p and Path(p).is_dir() and p not in (os.getcwd(), "")]
	if extra_paths:
		existing = env.get("PYTHONPATH", "")
		env["PYTHONPATH"] = os.pathsep.join([*extra_paths, existing]) if existing else os.pathsep.join(extra_paths)
	return env


def _get_daemon_pid() -> int | None:
	"""Read the daemon PID from the pid file, or None if not running."""
	if not DAEMON_PID_FILE.exists():
		return None

	try:
		pid = int(DAEMON_PID_FILE.read_text().strip())
		os.kill(pid, 0)
	except ValueError, OSError:
		DAEMON_PID_FILE.unlink(missing_ok=True)
		return None

	if not _is_daemon_process(pid):
		DAEMON_PID_FILE.unlink(missing_ok=True)
		return None

	return pid


def _is_daemon_process(pid: int) -> bool:
	"""Guard against PID reuse: verify the pid actually runs the sentinel daemon."""
	try:
		cmdline = psutil.Process(pid).cmdline()
	except psutil.Error:
		return False
	return any("sentinel_cli.daemon" in part for part in cmdline)


def _configure_daemon_logging() -> None:
	STATE_DIR.mkdir(parents=True, exist_ok=True)
	handler = RotatingFileHandler(
		STATE_DIR / "daemon.log",
		maxBytes=DEFAULT_LOG_ROTATION_MAX_BYTES,
		backupCount=DEFAULT_LOG_ROTATION_BACKUPS,
	)
	logging.basicConfig(
		level=logging.INFO,
		format="%(asctime)s %(levelname)s %(name)s: %(message)s",
		handlers=[handler],
	)


def _daemon_main_loop() -> None:
	"""Main loop for the daemon process (runs in background)."""
	_configure_daemon_logging()

	should_exit = False

	def signal_handler(signum: int, frame: object) -> None:
		nonlocal should_exit
		should_exit = True

	signal.signal(signal.SIGTERM, signal_handler)
	signal.signal(signal.SIGINT, signal_handler)

	monitor = RestartMonitor(check_interval=5.0)

	def on_restart(old_info: ProcessInfo, new_info: ProcessInfo) -> None:
		logger.info(f"Restarted {new_info.name} (old_pid: {old_info.pid}, new_pid: {new_info.pid})")

	monitor.set_restart_callback(on_restart)
	monitor.start()
	logger.info(f"Daemon started (pid: {os.getpid()})")

	try:
		while not should_exit:
			time.sleep(1)
	finally:
		monitor.stop()
		DAEMON_PID_FILE.unlink(missing_ok=True)
		logger.info("Daemon stopped")


@daemon_app.command()
def start() -> None:
	"""Start the restart monitor daemon"""
	existing_pid = _get_daemon_pid()
	if existing_pid:
		console.print(f"[yellow]⚠[/] Daemon already running (pid: {existing_pid})")
		return

	STATE_DIR.mkdir(parents=True, exist_ok=True)

	proc = subprocess.Popen(
		[sys.executable, "-m", "sentinel_cli.daemon", DAEMON_RUN_ARG],
		start_new_session=True,
		stdin=subprocess.DEVNULL,
		stdout=subprocess.DEVNULL,
		stderr=subprocess.DEVNULL,
		env=_daemon_subprocess_env(),
	)

	DAEMON_PID_FILE.write_text(str(proc.pid))
	console.print(f"[green]✓[/] Started daemon (pid: {proc.pid})")


@daemon_app.command()
def stop() -> None:
	"""Stop the restart monitor daemon"""
	pid = _get_daemon_pid()
	if not pid:
		console.print("[dim]Daemon is not running[/]")
		return

	try:
		os.kill(pid, signal.SIGTERM)
		console.print(f"[green]✓[/] Stopped daemon (pid: {pid})")
	except OSError as e:
		console.print(f"[red]✗[/] Failed to stop daemon: {e}")

	DAEMON_PID_FILE.unlink(missing_ok=True)


@daemon_app.command()
def status() -> None:
	"""Show daemon status"""
	pid = _get_daemon_pid()
	if pid:
		console.print(f"[green]●[/] Daemon is running (pid: {pid})")
	else:
		console.print("[dim]○[/] Daemon is not running")


def is_daemon_running() -> bool:
	"""Check if the daemon is currently running."""
	return _get_daemon_pid() is not None


def main() -> None:
	"""Module entry point: run the background monitor loop or the CLI app."""
	if sys.argv[1:2] == [DAEMON_RUN_ARG]:
		_daemon_main_loop()
	else:
		daemon_app()


if __name__ == "__main__":
	main()
