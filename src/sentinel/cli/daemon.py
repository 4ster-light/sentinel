"""Daemon commands for continuous process monitoring"""

import os
import signal
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console

from ..state import STATE_DIR

console = Console()
daemon_app = typer.Typer(name="daemon", help="Manage the restart monitor daemon", no_args_is_help=True)

DAEMON_PID_FILE: Path = STATE_DIR / "daemon.pid"


def _get_daemon_pid() -> int | None:
	"""Read the daemon PID from the pid file, or None if not running."""
	if not DAEMON_PID_FILE.exists():
		return None

	try:
		pid = int(DAEMON_PID_FILE.read_text().strip())
		os.kill(pid, 0)
		return pid
	except ValueError, OSError:
		DAEMON_PID_FILE.unlink(missing_ok=True)
		return None


def _daemon_main_loop() -> None:
	"""Main loop for the daemon process (runs in background)."""
	import signal
	import time

	from ..restart_monitor import RestartMonitor
	from ..state import ProcessInfo

	should_exit = False

	def signal_handler(signum: int, frame: object) -> None:
		nonlocal should_exit
		should_exit = True

	signal.signal(signal.SIGTERM, signal_handler)
	signal.signal(signal.SIGINT, signal_handler)

	monitor = RestartMonitor(check_interval=5.0)

	def on_restart(info: ProcessInfo) -> None:
		pass

	monitor.set_restart_callback(on_restart)
	monitor.start()

	try:
		while not should_exit:
			time.sleep(1)
	finally:
		monitor.stop()
		DAEMON_PID_FILE.unlink(missing_ok=True)


@daemon_app.command()
def start() -> None:
	"""Start the restart monitor daemon"""
	existing_pid = _get_daemon_pid()
	if existing_pid:
		console.print(f"[yellow]⚠[/] Daemon already running (pid: {existing_pid})")
		return

	STATE_DIR.mkdir(parents=True, exist_ok=True)

	proc = subprocess.Popen(
		[sys.executable, "-m", "sentinel.cli.daemon", "_run"],
		start_new_session=True,
		stdin=subprocess.DEVNULL,
		stdout=subprocess.DEVNULL,
		stderr=subprocess.DEVNULL,
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


if __name__ == "__main__" or (len(sys.argv) > 1 and sys.argv[1] == "_run"):
	if len(sys.argv) > 1 and sys.argv[1] == "_run":
		_daemon_main_loop()
	else:
		daemon_app()
