"""Daemon commands for continuous process monitoring"""

import fcntl
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Generator
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

import psutil
import typer
from rich.console import Console
from rich.markup import escape

from sentinel_core.logs import DEFAULT_LOG_ROTATION_BACKUPS, DEFAULT_LOG_ROTATION_MAX_BYTES
from sentinel_core.restart_monitor import RestartMonitor
from sentinel_core.state import STATE_DIR, ProcessInfo

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
	except ValueError, OSError:
		# A half-written file belongs to a daemon that is still starting; the
		# caller polls, so leave the child's file alone instead of deleting it.
		return None

	try:
		os.kill(pid, 0)
	except OSError:
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


def _write_daemon_pid(pid: int) -> None:
	"""Publish the pid atomically so a poll never sees a truncated file."""
	STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
	temporary = DAEMON_PID_FILE.with_name(f"{DAEMON_PID_FILE.name}.tmp")
	temporary.write_text(str(pid))
	os.replace(temporary, DAEMON_PID_FILE)


def _rotate_daemon_log(source: str, destination: str) -> None:
	"""Rotate the log in place, keeping the inherited stderr descriptor valid.

	Copying and then truncating keeps stderr pointing at the live file, at the
	cost of any bytes written between the two steps.
	"""
	shutil.copy2(source, destination)
	with open(source, "r+b") as active:
		active.truncate(0)


def _configure_daemon_logging() -> None:
	STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
	handler = RotatingFileHandler(
		STATE_DIR / "daemon.log",
		maxBytes=DEFAULT_LOG_ROTATION_MAX_BYTES,
		backupCount=DEFAULT_LOG_ROTATION_BACKUPS,
	)
	handler.rotator = _rotate_daemon_log
	logging.basicConfig(
		level=logging.INFO,
		format="%(asctime)s %(levelname)s %(name)s: %(message)s",
		handlers=[handler],
	)


@contextmanager
def _daemon_lock(name: str, blocking: bool = True) -> Generator[None]:
	STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
	with (STATE_DIR / name).open("a") as lock:
		fcntl.flock(lock, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
		try:
			yield
		finally:
			fcntl.flock(lock, fcntl.LOCK_UN)


def _daemon_main_loop() -> None:
	with _daemon_lock("daemon.lock", blocking=False):
		_run_monitor()


def _run_monitor() -> None:
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
	_write_daemon_pid(os.getpid())
	logger.info(f"Daemon started (pid: {os.getpid()})")

	try:
		while not should_exit:
			time.sleep(1)
	finally:
		monitor.stop()
		if DAEMON_PID_FILE.exists() and DAEMON_PID_FILE.read_text().strip() == str(os.getpid()):
			DAEMON_PID_FILE.unlink(missing_ok=True)
		logger.info("Daemon stopped")


@daemon_app.command()
def start() -> None:
	"""Start the restart monitor daemon"""
	with _daemon_lock("daemon-control.lock"):
		existing_pid = _get_daemon_pid()
		if existing_pid:
			console.print(f"[yellow]⚠[/] Daemon already running (pid: {existing_pid})")
			return
		try:
			with (STATE_DIR / "daemon.log").open("a") as stderr:
				proc = subprocess.Popen(
					[sys.executable, "-m", "sentinel_cli.daemon", DAEMON_RUN_ARG],
					start_new_session=True,
					stdin=subprocess.DEVNULL,
					stdout=subprocess.DEVNULL,
					stderr=stderr,
					env=_daemon_subprocess_env(),
				)
		except OSError as e:
			console.print(f"[red]✗[/] Failed to start daemon: {escape(str(e))}")
			raise typer.Exit(1) from None

		deadline = time.monotonic() + 10
		while proc.poll() is None and time.monotonic() < deadline:
			# Only the child publishes its PID, after initialization succeeds.
			if _get_daemon_pid() == proc.pid:
				console.print(f"[green]✓[/] Started daemon (pid: {proc.pid})")
				return
			time.sleep(0.05)
		if proc.poll() is None:
			proc.kill()
			proc.wait()
		console.print(f"[red]✗[/] Daemon failed to start. See {escape(str(STATE_DIR / 'daemon.log'))}")
		raise typer.Exit(1)


@daemon_app.command()
def stop() -> None:
	"""Stop the restart monitor daemon"""
	with _daemon_lock("daemon-control.lock"):
		pid = _get_daemon_pid()
		if not pid:
			console.print("[dim]Daemon is not running[/]")
			return
		try:
			proc = psutil.Process(pid)
			proc.terminate()
			# The daemon leaves its loop within a second but may spend up to ten
			# seconds joining the monitor thread.
			try:
				proc.wait(timeout=15)
			except psutil.TimeoutExpired:
				proc.kill()
				proc.wait(timeout=5)
		except psutil.NoSuchProcess:
			pass
		except (OSError, psutil.Error) as e:
			console.print(f"[red]✗[/] Failed to stop daemon: {escape(str(e))}")
			raise typer.Exit(1) from None
		console.print(f"[green]✓[/] Stopped daemon (pid: {pid})")


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
