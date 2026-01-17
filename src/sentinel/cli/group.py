"""Group management commands"""

from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from ..process import batch_restart_processes, batch_start_processes, batch_stop_processes
from ..state import State

console = Console()
group_app = typer.Typer(
	name="group",
	help="Process group management",
	no_args_is_help=True,
)


@group_app.command("create")
def group_create(
	name: Annotated[str, typer.Argument(help="Group name")],
	env: Annotated[list[str], typer.Option("--env", "-e", help="Environment variables (KEY=VALUE)")] = [],
	env_file: Annotated[str | None, typer.Option("--env-file", "-f", help="Path to .env file")] = None,
) -> None:
	"""Create a new process group"""
	state = State()

	# Parse env vars
	env_dict: dict[str, str] = {}
	for env_var in env:
		if "=" not in env_var:
			console.print(f"[red]✗[/] Invalid environment variable: {env_var} (expected KEY=VALUE)")
			raise typer.Exit(1)
		key, value = env_var.split("=", 1)
		env_dict[key] = value

	# Validate env_file if provided
	if env_file:
		from pathlib import Path

		if not Path(env_file).exists():
			console.print(f"[red]✗[/] Environment file not found: {env_file}")
			raise typer.Exit(1)

	group = state.create_group(name, env=env_dict if env_dict else None, env_file=env_file)

	if group:
		console.print(f"[green]✓[/] Created group [bold]{name}[/]")
	else:
		console.print(f"[red]✗[/] Group '{name}' already exists")
		raise typer.Exit(1)


@group_app.command("add")
def group_add(
	group_name: Annotated[str, typer.Argument(help="Group name")],
	process_id: Annotated[int, typer.Argument(help="Process ID")],
) -> None:
	"""Add a process to a group"""
	state = State()

	if not state.add_process_to_group(group_name, process_id):
		group = state.get_group(group_name)
		process = state.get_process(process_id)

		if not group:
			console.print(f"[red]✗[/] Group '{group_name}' not found")
		elif not process:
			console.print(f"[red]✗[/] Process {process_id} not found")
		else:
			console.print(f"[red]✗[/] Failed to add process to group")

		raise typer.Exit(1)

	process = state.get_process(process_id)
	if process:
		console.print(f"[green]✓[/] Added process [bold]{process.name}[/] to group [bold]{group_name}[/]")


@group_app.command("remove")
def group_remove(
	process_id: Annotated[int, typer.Argument(help="Process ID")],
) -> None:
	"""Remove a process from its group"""
	state = State()

	process = state.get_process(process_id)
	if not process:
		console.print(f"[red]✗[/] Process {process_id} not found")
		raise typer.Exit(1)

	if not process.group:
		console.print(f"[yellow]⚠[/] Process [bold]{process.name}[/] is not in any group")
		return

	old_group = process.group
	state.remove_process_from_group(process_id)

	console.print(f"[green]✓[/] Removed process [bold]{process.name}[/] from group [bold]{old_group}[/]")


@group_app.command("list")
def group_list(
	name: Annotated[str | None, typer.Argument(help="Group name (optional)")] = None,
) -> None:
	"""List process groups and their processes"""
	state = State()

	if name:
		# List specific group
		group = state.get_group(name)
		if not group:
			console.print(f"[red]✗[/] Group '{name}' not found")
			raise typer.Exit(1)

		processes = state.get_processes_in_group(name)
		console.print(f"\n[bold]Group: {name}[/]")
		console.print(f"Created: {group.created_at}")
		if group.env_file:
			console.print(f"Environment file: {group.env_file}")
		if group.env:
			console.print(f"Environment variables:")
			for key, value in group.env.items():
				console.print(f"  {key}={value}")

		if processes:
			console.print(f"\nProcesses ({len(processes)}):")
			for process in processes:
				console.print(f"  - {process.name} (id: {process.id}, pid: {process.pid})")
		else:
			console.print("Processes: none")
		console.print()
	else:
		# List all groups
		groups = state.list_groups()

		if not groups:
			console.print("[dim]No groups found[/]")
			return

		table = Table(show_header=True, header_style="bold")
		table.add_column("GROUP", style="bold")
		table.add_column("PROCESSES", justify="right")
		table.add_column("ENV VARS", justify="right")
		table.add_column("CREATED")

		for group in groups:
			process_count = len(state.get_processes_in_group(group.name))
			env_count = len(group.env)
			table.add_row(
				group.name,
				str(process_count),
				str(env_count),
				group.created_at,
			)

		console.print(table)


@group_app.command("start")
def group_start(
	group_name: Annotated[str, typer.Argument(help="Group name")],
) -> None:
	"""Start all processes in a group"""
	state = State()

	group = state.get_group(group_name)
	if not group:
		console.print(f"[red]✗[/] Group '{group_name}' not found")
		raise typer.Exit(1)

	processes = state.get_processes_in_group(group_name)

	if not processes:
		console.print(f"[dim]No processes in group '{group_name}'[/]")
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


@group_app.command("stop")
def group_stop(
	group_name: Annotated[str, typer.Argument(help="Group name")],
	force: Annotated[bool, typer.Option("--force", "-f", help="Force kill all")] = False,
) -> None:
	"""Stop all processes in a group"""
	state = State()

	group = state.get_group(group_name)
	if not group:
		console.print(f"[red]✗[/] Group '{group_name}' not found")
		raise typer.Exit(1)

	processes = state.get_processes_in_group(group_name)

	if not processes:
		console.print(f"[dim]No processes in group '{group_name}'[/]")
		return

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


@group_app.command("restart")
def group_restart(
	group_name: Annotated[str, typer.Argument(help="Group name")],
) -> None:
	"""Restart all processes in a group"""
	state = State()

	group = state.get_group(group_name)
	if not group:
		console.print(f"[red]✗[/] Group '{group_name}' not found")
		raise typer.Exit(1)

	processes = state.get_processes_in_group(group_name)

	if not processes:
		console.print(f"[dim]No processes in group '{group_name}'[/]")
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


@group_app.command("delete")
def group_delete(
	group_name: Annotated[str, typer.Argument(help="Group name")],
	with_processes: Annotated[
		bool, typer.Option("--with-processes", help="Stop and remove all processes in the group")
	] = False,
) -> None:
	"""Delete a process group"""
	state = State()

	group = state.get_group(group_name)
	if not group:
		console.print(f"[red]✗[/] Group '{group_name}' not found")
		raise typer.Exit(1)

	processes = state.get_processes_in_group(group_name)

	if with_processes and processes:
		# Stop all processes in the group
		successful, failed = batch_stop_processes(state, processes)

		for info in successful:
			console.print(f"[green]✓[/] Stopped [bold]{info.name}[/]")

		for info, error in failed:
			console.print(f"[red]✗[/] Failed to stop {info.name}: {error}")

	# Delete the group (which also unassigns processes)
	state.remove_group(group_name)

	console.print(f"[green]✓[/] Deleted group [bold]{group_name}[/]")
	if processes:
		if with_processes:
			console.print(f"[green]✓[/] Stopped {len(processes)} process(es)")
		else:
			console.print(f"[yellow]⚠[/] {len(processes)} process(es) unassigned from group")
