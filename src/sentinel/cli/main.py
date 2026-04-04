"""Main process commands"""

from datetime import datetime
from typing import Annotated

import psutil
import typer
from rich.console import Console
from rich.table import Table

from ..logs import clear_logs, show_logs
from ..process import (
	batch_restart_processes,
	batch_start_processes,
	batch_stop_processes,
	get_process_status,
	restart_process,
	start_process,
	stop_process,
)
from ..restart_monitor import check_and_restart_processes
from ..state import HealthCheckConfig, ProcessInfo, State
from .daemon import is_daemon_running

console = Console()


def _perform_lazy_restart_check(state: State) -> None:
	"""Perform a one-time check for dead processes and restart/cleanup as needed."""

	def on_restart(old_info: ProcessInfo, new_info: ProcessInfo) -> None:
		console.print(
			f"[yellow]⚠[/] Auto-restarted [bold]{new_info.name}[/] (old_pid: {old_info.pid}, new_pid: {new_info.pid})"
		)

	def on_cleanup(info: ProcessInfo) -> None:
		console.print(f"[dim]Cleaned up dead process [bold]{info.name}[/] (id: {info.id})[/]")

	restarted, cleaned_up = check_and_restart_processes(state, on_restart=on_restart, on_cleanup=on_cleanup)

	if restarted or cleaned_up:
		console.print()


def _format_uptime(started_at: str) -> str:
	start = datetime.fromisoformat(started_at)
	delta = datetime.now() - start
	secs = int(delta.total_seconds())

	if secs < 60:
		return f"{secs}s"
	elif secs < 3600:
		return f"{secs // 60}m {secs % 60}s"
	elif secs < 86400:
		return f"{secs // 3600}h {(secs % 3600) // 60}m"
	else:
		return f"{secs // 86400}d {(secs % 86400) // 3600}h"


def _format_memory(mb: float) -> str:
	if mb < 1:
		return f"{mb * 1024:.0f}KB"
	elif mb < 1024:
		return f"{mb:.1f}MB"
	else:
		return f"{mb / 1024:.2f}GB"


def _parse_ionice_option(raw: str | None) -> tuple[str | None, int | None]:
	if raw is None or not raw.strip():
		return None, None
	s = raw.strip().lower()
	if s == "idle":
		return "idle", None
	if s == "best-effort" or s.startswith("best-effort:"):
		rest = s.removeprefix("best-effort").lstrip(":").strip()
		if not rest:
			return "best_effort", None
		try:
			value = int(rest)
		except ValueError as e:
			raise ValueError(f"invalid ionice priority in {raw!r}") from e
		if not 0 <= value <= 7:
			raise ValueError("ionice best-effort priority must be between 0 and 7")
		return "best_effort", value
	if s == "realtime" or s.startswith("realtime:"):
		rest = s.removeprefix("realtime").lstrip(":").strip()
		if not rest:
			return "realtime", None
		try:
			value = int(rest)
		except ValueError as e:
			raise ValueError(f"invalid ionice priority in {raw!r}") from e
		if not 0 <= value <= 7:
			raise ValueError("ionice realtime priority must be between 0 and 7")
		return "realtime", value
	raise ValueError("invalid --ionice value (use idle, best-effort[:0-7], or realtime[:0-7])")


def register_main_commands(app: typer.Typer) -> None:
	"""Register all main commands with the app"""

	@app.command()
	def run(
		command: Annotated[list[str], typer.Argument(help="Command to run")],
		name: Annotated[str | None, typer.Option("--name", "-n", help="Process name")] = None,
		restart: Annotated[bool, typer.Option("--restart", "-r", help="Auto-restart on exit")] = False,
		user: Annotated[
			str | None,
			typer.Option("--user", "-u", help="Run process as this system user (name or uid)"),
		] = None,
		group: Annotated[str | None, typer.Option("--group", "-g", help="Process group")] = None,
		env_file: Annotated[str | None, typer.Option("--env-file", "-e", help="Path to .env file")] = None,
		cwd: Annotated[str | None, typer.Option("--cwd", help="Working directory for the process")] = None,
		health_http: Annotated[str | None, typer.Option("--health-http", help="HTTP health check URL")] = None,
		health_tcp: Annotated[
			str | None, typer.Option("--health-tcp", help="TCP health check target host:port")
		] = None,
		health_interval: Annotated[
			float,
			typer.Option("--health-interval", help="Health check interval in seconds"),
		] = 30.0,
		health_timeout: Annotated[
			float,
			typer.Option("--health-timeout", help="Health check timeout in seconds"),
		] = 3.0,
		health_failures: Annotated[
			int,
			typer.Option("--health-failures", help="Consecutive health check failures before restart"),
		] = 3,
		startup_timeout: Annotated[
			float | None,
			typer.Option(
				"--startup-timeout",
				"-S",
				help="Wait up to this many seconds; fail if the process exits before then",
			),
		] = None,
		nice: Annotated[
			int | None,
			typer.Option("--nice", help="Nice value (-20 to 19) for the process"),
		] = None,
		ionice: Annotated[
			str | None,
			typer.Option(
				"--ionice",
				help="I/O scheduling class: idle, best-effort[:0-7], or realtime[:0-7]",
			),
		] = None,
	) -> None:
		"""Start a background process"""
		state = State()
		cmd = " ".join(command)
		health_check: HealthCheckConfig | None = None

		if startup_timeout is not None and startup_timeout <= 0:
			console.print("[red]✗[/] --startup-timeout must be greater than 0")
			raise typer.Exit(1)

		if nice is not None and not -20 <= nice <= 19:
			console.print("[red]✗[/] --nice must be between -20 and 19")
			raise typer.Exit(1)

		try:
			ionice_ioclass, ionice_value = _parse_ionice_option(ionice)
		except ValueError as e:
			console.print(f"[red]✗[/] {e}")
			raise typer.Exit(1)

		if health_http and health_tcp:
			console.print("[red]✗[/] Use only one of --health-http or --health-tcp")
			raise typer.Exit(1)

		if health_interval <= 0:
			console.print("[red]✗[/] --health-interval must be greater than 0")
			raise typer.Exit(1)

		if health_timeout <= 0:
			console.print("[red]✗[/] --health-timeout must be greater than 0")
			raise typer.Exit(1)

		if health_failures < 1:
			console.print("[red]✗[/] --health-failures must be at least 1")
			raise typer.Exit(1)

		if health_http:
			health_check = HealthCheckConfig(
				kind="http",
				target=health_http,
				interval_seconds=health_interval,
				timeout_seconds=health_timeout,
				failure_threshold=health_failures,
			)
		elif health_tcp:
			health_check = HealthCheckConfig(
				kind="tcp",
				target=health_tcp,
				interval_seconds=health_interval,
				timeout_seconds=health_timeout,
				failure_threshold=health_failures,
			)

		try:
			priority_notes: list[str] = []
			info = start_process(
				state,
				cmd,
				name=name,
				restart=restart,
				user=user,
				env_file=env_file,
				cwd=cwd,
				health_check=health_check,
				startup_timeout_seconds=startup_timeout,
				nice=nice,
				ionice_ioclass=ionice_ioclass,
				ionice_value=ionice_value,
				priority_warnings=priority_notes,
			)
			for note in priority_notes:
				console.print(f"[yellow]⚠[/] {note}")
			if priority_notes:
				console.print()
			if group:
				if not state.add_process_to_group(group, info.id):
					console.print(
						f"[yellow]⚠[/] Group '{group}' does not exist. Process started but not added to group."
					)
				else:
					console.print(
						f"[green]✓[/] Started [bold]{info.name}[/] (id: {info.id}, pid: {info.pid}) in group [bold]{group}[/]"
					)
			else:
				console.print(f"[green]✓[/] Started [bold]{info.name}[/] (id: {info.id}, pid: {info.pid})")

			if restart and not is_daemon_running():
				console.print(
					"[yellow]⚠[/] Restart flag set but daemon is not running. "
					"Restarts will only happen when you run other sentinel commands."
				)
				console.print("[dim]  Run 'sentinel daemon start' for continuous monitoring.[/]")

			if health_check and not is_daemon_running():
				console.print(
					"[yellow]⚠[/] Health checks are configured but daemon is not running. "
					"Checks will only happen when you run other sentinel commands."
				)
				console.print("[dim]  Run 'sentinel daemon start' for continuous monitoring.[/]")
		except ValueError as e:
			console.print(f"[red]✗[/] {e}")
			raise typer.Exit(1)

	@app.command()
	def stop(
		id_or_name: Annotated[str, typer.Argument(help="Process ID or name")],
		force: Annotated[bool, typer.Option("--force", "-f", help="Force kill with SIGKILL")] = False,
	) -> None:
		"""Stop a running process"""
		state = State()

		# Try to parse as int (ID), otherwise treat as name
		try:
			target = int(id_or_name)
		except ValueError:
			target = id_or_name

		try:
			info = stop_process(state, target, force=force)
			console.print(f"[green]✓[/] Stopped [bold]{info.name}[/] (id: {info.id})")
		except ValueError as e:
			console.print(f"[red]✗[/] {e}")
			raise typer.Exit(1)

	@app.command()
	def restart(
		id_or_name: Annotated[str, typer.Argument(help="Process ID or name")],
	) -> None:
		"""Restart a process"""
		state = State()

		try:
			target: int | str = int(id_or_name)
		except ValueError:
			target = id_or_name

		try:
			info = restart_process(state, target)
			console.print(f"[green]✓[/] Restarted [bold]{info.name}[/] (id: {info.id}, pid: {info.pid})")
		except ValueError as e:
			console.print(f"[red]✗[/] {e}")
			raise typer.Exit(1)

	@app.command(name="list")
	def list_cmd() -> None:
		"""List all managed processes"""
		state = State()
		_perform_lazy_restart_check(state)
		processes = state.list_processes()

		if not processes:
			console.print("[dim]No processes running[/]")
			return

		table = Table(show_header=True, header_style="bold")
		table.add_column("ID", style="cyan", justify="right")
		table.add_column("NAME", style="bold")
		table.add_column("PID", justify="right")
		table.add_column("STATUS")
		table.add_column("CPU", justify="right")
		table.add_column("MEM", justify="right")
		table.add_column("UPTIME", justify="right")
		table.add_column("RESTART")
		table.add_column("USER")
		table.add_column("GROUP", style="magenta")
		table.add_column("COMMAND", max_width=40)

		for info in processes:
			status = get_process_status(info)
			status_str = "[green]running[/]" if status["running"] else "[red]stopped[/]"
			restart_str = "[green]✓[/]" if info.restart else "[dim]-[/]"
			user_str = info.user if info.user else "[dim]-[/]"
			group_str = info.group if info.group else "[dim]-[/]"

			table.add_row(
				str(info.id),
				info.name,
				str(info.pid),
				status_str,
				f"{status['cpu_percent']:.1f}%",
				_format_memory(status["memory_mb"]),
				_format_uptime(info.started_at),
				restart_str,
				user_str,
				group_str,
				info.cmd[:40] + "..." if len(info.cmd) > 40 else info.cmd,
			)

		console.print(table)

	@app.command()
	def status(
		id_or_name: Annotated[str, typer.Argument(help="Process ID or name")],
	) -> None:
		"""Show detailed status of a process"""
		state = State()
		_perform_lazy_restart_check(state)

		try:
			target = int(id_or_name)
		except ValueError:
			target = id_or_name

		if isinstance(target, int):
			info = state.get_process(target)
		else:
			info = state.find_process_by_name(target)

		if not info:
			console.print(f"[red]✗[/] Process not found: {id_or_name}")
			raise typer.Exit(1)

		proc_status = get_process_status(info)

		console.print(f"\n[bold]{info.name}[/] (id: {info.id})")
		console.print(f"  PID:       {info.pid}")
		console.print(f"  Status:    {'[green]running[/]' if proc_status['running'] else '[red]stopped[/]'}")
		console.print(f"  CPU:       {proc_status['cpu_percent']:.1f}%")
		console.print(f"  Memory:    {_format_memory(proc_status['memory_mb'])}")
		console.print(f"  Uptime:    {_format_uptime(info.started_at)}")
		console.print(f"  Restart:   {'yes' if info.restart else 'no'}")
		console.print(f"  User:      {info.user if info.user else 'default'}")
		console.print(f"  Group:     {info.group if info.group else 'none'}")
		console.print(f"  CWD:       {info.cwd}")
		console.print(f"  Command:   {info.cmd}")
		console.print(f"  Stdout:    {info.stdout_log}")
		console.print(f"  Stderr:    {info.stderr_log}")

	@app.command()
	def logs(
		id_or_name: Annotated[str, typer.Argument(help="Process ID or name")],
		lines: Annotated[int, typer.Option("--lines", "-n", help="Number of lines to show")] = 50,
		follow: Annotated[bool, typer.Option("--follow", "-f", help="Follow log output")] = False,
		stream: Annotated[
			str,
			typer.Option("--stream", "-s", help="Stream to show: stdout, stderr, or both"),
		] = "both",
		clear: Annotated[bool, typer.Option("--clear", "-c", help="Clear logs")] = False,
	) -> None:
		"""View process logs"""
		state = State()

		try:
			target: int | str = int(id_or_name)
		except ValueError:
			target = id_or_name

		if isinstance(target, int):
			info = state.get_process(target)
		else:
			info = state.find_process_by_name(target)

		if not info:
			console.print(f"[red]✗[/] Process not found: {id_or_name}")
			raise typer.Exit(1)

		if clear:
			clear_logs(info.stdout_log, info.stderr_log)
			console.print(f"[green]✓[/] Cleared logs for [bold]{info.name}[/]")
			return

		show_logs(info.stdout_log, info.stderr_log, lines=lines, follow=follow, stream=stream)

	@app.command()
	def clean() -> None:
		"""Remove dead processes from state"""
		state = State()
		removed = []

		for info in list(state.processes.values()):
			if not psutil.pid_exists(info.pid):
				state.remove_process(info.id)
				removed.append(info)

		if removed:
			for info in removed:
				console.print(f"[yellow]✓[/] Removed dead process [bold]{info.name}[/] (id: {info.id})")
		else:
			console.print("[dim]No dead processes found[/]")

	@app.command()
	def stopall(
		force: Annotated[bool, typer.Option("--force", "-f", help="Force kill all")] = False,
	) -> None:
		"""Stop all managed processes"""
		state = State()
		processes = state.list_processes()
		successful, failed = batch_stop_processes(state, processes, force=force)

		for info in successful:
			console.print(f"[green]✓[/] Stopped [bold]{info.name}[/]")

		for info, error in failed:
			console.print(f"[red]✗[/] Failed to stop {info.name}: {error}")

		if successful:
			console.print(f"\n[green]Stopped {len(successful)} process(es)[/]", end="")
			if failed:
				console.print(f", [red]failed {len(failed)} process(es)[/]")
			else:
				console.print()

	@app.command()
	def startall() -> None:
		"""Start all managed processes"""
		state = State()
		processes = state.list_processes()

		if not processes:
			console.print("[dim]No processes to start[/]")
			return

		successful, failed = batch_start_processes(state, processes)

		for info in successful:
			console.print(f"[green]✓[/] Started [bold]{info.name}[/] (pid: {info.pid})")

		for info, error in failed:
			console.print(f"[red]✗[/] Failed to start {info.name}: {error}")

		if successful:
			console.print(f"\n[green]Started {len(successful)} process(es)[/]", end="")
			if failed:
				console.print(f", [red]failed {len(failed)} process(es)[/]")
			else:
				console.print()

	@app.command()
	def restartall() -> None:
		"""Restart all managed processes"""
		state = State()
		processes = state.list_processes()

		if not processes:
			console.print("[dim]No processes to restart[/]")
			return

		successful, failed = batch_restart_processes(state, processes)

		for info in successful:
			console.print(f"[green]✓[/] Restarted [bold]{info.name}[/] (pid: {info.pid})")

		for info, error in failed:
			console.print(f"[red]✗[/] Failed to restart {info.name}: {error}")

		if successful:
			console.print(f"\n[green]Restarted {len(successful)} process(es)[/]", end="")
			if failed:
				console.print(f", [red]failed {len(failed)} process(es)[/]")
			else:
				console.print()
