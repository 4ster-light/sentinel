"""Main process commands"""

import shlex
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from sentinel_core.format import format_memory_mb, format_uptime_seconds, uptime_from_started_at
from sentinel_core.logs import clear_logs, show_logs
from sentinel_core.options import StartOptions
from sentinel_core.process import (
	batch_restart_processes,
	batch_start_processes,
	batch_stop_processes,
	cleanup_dead_processes,
	get_process_status,
	restart_process,
	start_process,
	stop_process,
)
from sentinel_core.restart_monitor import check_and_restart_processes
from sentinel_core.state import ProcessInfo, State
from .common import console as error_console
from .common import load_state
from .daemon import is_daemon_running

console = Console()


def _perform_lazy_restart_check(state: State) -> None:
	"""Perform a one-time check for dead processes and restart/cleanup as needed."""
	if is_daemon_running():
		return

	def on_restart(old_info: ProcessInfo, new_info: ProcessInfo) -> None:
		console.print(
			f"[yellow]⚠[/] Auto-restarted [bold]{escape(new_info.name)}[/] (old_pid: {old_info.pid}, new_pid: {new_info.pid})"
		)

	def on_cleanup(info: ProcessInfo) -> None:
		console.print(f"[dim]Cleaned up dead process [bold]{escape(info.name)}[/] (id: {info.id})[/]")

	restarted, cleaned_up = check_and_restart_processes(state, on_restart=on_restart, on_cleanup=on_cleanup)

	if restarted or cleaned_up:
		console.print()


def register_main_commands(app: typer.Typer) -> None:
	"""Register all main commands with the app"""

	@app.command()
	def run(
		command: Annotated[list[str], typer.Argument(help="Command to run")],
		shell: Annotated[
			bool,
			typer.Option("--shell", help="Interpret one command string with shell syntax"),
		] = False,
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
		instances: Annotated[
			int,
			typer.Option("--instances", "-c", help="Number of instances to start"),
		] = 1,
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
		state = load_state()
		if shell and len(command) != 1:
			error_console.print("[red]✗[/] --shell requires one command string")
			raise typer.Exit(1)
		if not command[0].strip():
			error_console.print("[red]✗[/] Command cannot be empty")
			raise typer.Exit(1)
		cmd = command[0] if shell else shlex.join(command)
		try:
			command_name = shlex.split(command[0])[0] if shell else command[0]
		except ValueError, IndexError:
			error_console.print("[red]✗[/] Command must contain a valid executable name")
			raise typer.Exit(1)

		options = StartOptions(
			cmd=cmd,
			name=name,
			restart=restart,
			user=user,
			group=group,
			env_file=env_file,
			cwd=cwd,
			health_http=health_http,
			health_tcp=health_tcp,
			health_interval=health_interval,
			health_timeout=health_timeout,
			health_failures=health_failures,
			startup_timeout_seconds=startup_timeout,
			instances=instances,
			nice=nice,
			ionice=ionice,
		)

		try:
			options.validate()
		except ValueError as e:
			error_console.print(f"[red]✗[/] {escape(str(e))}")
			raise typer.Exit(1)

		health_check = options.health_check
		ionice_ioclass, ionice_value = options.ionice_spec()
		base_name = name or command_name.split("/")[-1]
		started_infos: list[ProcessInfo] = []
		cluster_mode = options.instances > 1

		try:
			for index in range(1, options.instances + 1):
				instance_name = f"{base_name}-{index}" if cluster_mode else base_name
				priority_notes: list[str] = []
				info = start_process(
					state,
					cmd,
					name=instance_name,
					restart=options.restart,
					user=options.user,
					group=options.group,
					env_file=options.env_file,
					cwd=options.cwd,
					health_check=health_check,
					startup_timeout_seconds=options.startup_timeout_seconds,
					nice=options.nice,
					ionice_ioclass=ionice_ioclass,
					ionice_value=ionice_value,
					priority_warnings=priority_notes,
				)
				started_infos.append(info)
				for note in priority_notes:
					console.print(f"[yellow]⚠[/] {escape(note)}")
				if priority_notes:
					console.print()
				group_label = f" in group [bold]{escape(group)}[/]" if group else ""
				console.print(
					f"[green]✓[/] Started [bold]{escape(info.name)}[/] (id: {info.id}, pid: {info.pid}){group_label}"
				)

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

			if cluster_mode:
				console.print(f"[green]✓[/] Started {len(started_infos)} instance(s) of [bold]{escape(base_name)}[/]")
		except ValueError as e:
			error_console.print(f"[red]✗[/] {escape(str(e))}")
			raise typer.Exit(1)

	@app.command()
	def stop(
		id_or_name: Annotated[str, typer.Argument(help="Process ID or name")],
		force: Annotated[bool, typer.Option("--force", "-f", help="Force kill with SIGKILL")] = False,
	) -> None:
		"""Stop a running process"""
		state = load_state()

		try:
			info = stop_process(state, id_or_name, force=force)
			console.print(f"[green]✓[/] Stopped [bold]{escape(info.name)}[/] (id: {info.id})")
		except ValueError as e:
			error_console.print(f"[red]✗[/] {escape(str(e))}")
			raise typer.Exit(1)

	@app.command()
	def restart(
		id_or_name: Annotated[str, typer.Argument(help="Process ID or name")],
	) -> None:
		"""Restart a process"""
		state = load_state()

		try:
			info = restart_process(state, id_or_name)
			console.print(f"[green]✓[/] Restarted [bold]{escape(info.name)}[/] (id: {info.id}, pid: {info.pid})")
		except ValueError as e:
			error_console.print(f"[red]✗[/] {escape(str(e))}")
			raise typer.Exit(1)

	@app.command(name="list")
	def list_cmd() -> None:
		"""List all managed processes"""
		state = load_state()
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
			status_str = "[green]running[/]" if status.running else f"[red]{status.status}[/]"
			restart_str = "[green]✓[/]" if info.restart else "[dim]-[/]"
			user_str = escape(info.user) if info.user else "[dim]-[/]"
			group_str = escape(info.group) if info.group else "[dim]-[/]"

			table.add_row(
				str(info.id),
				escape(info.name),
				str(info.pid),
				status_str,
				f"{status.cpu_percent:.1f}%",
				format_memory_mb(status.memory_mb),
				format_uptime_seconds(uptime_from_started_at(info.started_at)),
				restart_str,
				user_str,
				group_str,
				escape(info.cmd[:40] + "..." if len(info.cmd) > 40 else info.cmd),
			)

		console.print(table)

	@app.command()
	def status(
		id_or_name: Annotated[str, typer.Argument(help="Process ID or name")],
	) -> None:
		"""Show detailed status of a process"""
		state = load_state()
		_perform_lazy_restart_check(state)

		info = state.find_process(id_or_name)

		if not info:
			error_console.print(f"[red]✗[/] Process not found: {escape(id_or_name)}")
			raise typer.Exit(1)

		proc_status = get_process_status(info)

		console.print(f"\n[bold]{escape(info.name)}[/] (id: {info.id})")
		console.print(f"  PID:       {info.pid}")
		console.print(f"  Status:    {'[green]running[/]' if proc_status.running else f'[red]{proc_status.status}[/]'}")
		console.print(f"  CPU:       {proc_status.cpu_percent:.1f}%")
		console.print(f"  Memory:    {format_memory_mb(proc_status.memory_mb)}")
		console.print(f"  Uptime:    {format_uptime_seconds(uptime_from_started_at(info.started_at))}")
		console.print(f"  Restart:   {'yes' if info.restart else 'no'}")
		console.print(f"  User:      {escape(info.user) if info.user else 'default'}")
		console.print(f"  Group:     {escape(info.group) if info.group else 'none'}")
		console.print(f"  CWD:       {escape(info.cwd)}")
		console.print(f"  Command:   {escape(info.cmd)}")
		console.print(f"  Stdout:    {escape(info.stdout_log)}")
		console.print(f"  Stderr:    {escape(info.stderr_log)}")

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
		state = load_state()

		info = state.find_process(id_or_name)

		if not info:
			error_console.print(f"[red]✗[/] Process not found: {escape(id_or_name)}")
			raise typer.Exit(1)

		if clear:
			clear_logs(info.stdout_log, info.stderr_log)
			console.print(f"[green]✓[/] Cleared logs for [bold]{info.name}[/]")
			return

		show_logs(info.stdout_log, info.stderr_log, lines=lines, follow=follow, stream=stream)

	@app.command()
	def clean() -> None:
		"""Remove dead processes from state"""
		state = load_state()
		removed = cleanup_dead_processes(state)

		if removed:
			for info in removed:
				console.print(f"[yellow]✓[/] Removed dead process [bold]{escape(info.name)}[/] (id: {info.id})")
		else:
			console.print("[dim]No dead processes found[/]")

	@app.command()
	def stopall(
		force: Annotated[bool, typer.Option("--force", "-f", help="Force kill all")] = False,
	) -> None:
		"""Stop all managed processes"""
		state = load_state()
		processes = state.list_processes()
		successful, failed = batch_stop_processes(state, processes, force=force)

		for info in successful:
			console.print(f"[green]✓[/] Stopped [bold]{escape(info.name)}[/]")

		for info, error in failed:
			error_console.print(f"[red]✗[/] Failed to stop {escape(info.name)}: {escape(error)}")

		if successful:
			console.print(f"\n[green]Stopped {len(successful)} process(es)[/]", end="")
			if failed:
				console.print(f", [red]failed {len(failed)} process(es)[/]")
			else:
				console.print()
		if failed:
			raise typer.Exit(1)

	@app.command()
	def startall() -> None:
		"""Start all managed processes"""
		state = load_state()
		processes = state.list_processes()

		if not processes:
			console.print("[dim]No processes to start[/]")
			return

		successful, failed = batch_start_processes(state, processes)

		for info in successful:
			console.print(f"[green]✓[/] Started [bold]{escape(info.name)}[/] (pid: {info.pid})")

		for info, error in failed:
			error_console.print(f"[red]✗[/] Failed to start {escape(info.name)}: {escape(error)}")

		if successful:
			console.print(f"\n[green]Started {len(successful)} process(es)[/]", end="")
			if failed:
				console.print(f", [red]failed {len(failed)} process(es)[/]")
			else:
				console.print()
		if failed:
			raise typer.Exit(1)

	@app.command()
	def restartall() -> None:
		"""Restart all managed processes"""
		state = load_state()
		processes = state.list_processes()

		if not processes:
			console.print("[dim]No processes to restart[/]")
			return

		successful, failed = batch_restart_processes(state, processes)

		for info in successful:
			console.print(f"[green]✓[/] Restarted [bold]{escape(info.name)}[/] (pid: {info.pid})")

		for info, error in failed:
			error_console.print(f"[red]✗[/] Failed to restart {escape(info.name)}: {escape(error)}")

		if successful:
			console.print(f"\n[green]Restarted {len(successful)} process(es)[/]", end="")
			if failed:
				console.print(f", [red]failed {len(failed)} process(es)[/]")
			else:
				console.print()
		if failed:
			raise typer.Exit(1)
