"""Remote host management commands"""

from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from sentinel_core.remote import RemoteResult, format_remote, run_remote_sentinel
from sentinel_core.state import RemoteInfo
from .common import load_state

console = Console()
remote_app = typer.Typer(name="remote", help="Manage remote hosts via SSH", no_args_is_help=True)


def _print_remote_result(result: RemoteResult) -> None:
	if result.stdout:
		console.print(result.stdout, end="")
	if result.stderr:
		console.print(result.stderr, end="", style="red")
	if result.returncode != 0:
		raise typer.Exit(result.returncode)


@remote_app.command("add")
def remote_add(
	host: Annotated[str, typer.Argument(help="Remote host")],
	user: Annotated[str | None, typer.Option("--user", "-u", help="SSH user")] = None,
	port: Annotated[int | None, typer.Option("--port", "-p", help="SSH port")] = None,
) -> None:
	"""Register a remote host"""
	state = load_state()
	info = RemoteInfo(host=host, user=user, port=port)
	added = state.add_remote(info)
	if added is None:
		console.print(f"[red]✗[/] Remote host '{host}' is already registered")
		raise typer.Exit(1)
	console.print(f"[green]✓[/] Added remote [bold]{format_remote(added)}[/]")


@remote_app.command("remove")
def remote_remove(
	host: Annotated[str, typer.Argument(help="Remote host")],
) -> None:
	"""Unregister a remote host"""
	state = load_state()
	if state.remove_remote(host):
		console.print(f"[green]✓[/] Removed remote [bold]{host}[/]")
	else:
		console.print(f"[red]✗[/] Remote host '{host}' not found")
		raise typer.Exit(1)


@remote_app.command("list")
def remote_list(
	host: Annotated[str | None, typer.Argument(help="Optional remote host to run 'sentinel list' on")] = None,
) -> None:
	"""List registered remote hosts, or run 'sentinel list' on a remote host"""
	if host is not None:
		state = load_state()
		remote = state.get_remote(host)
		if remote is None:
			console.print(f"[red]✗[/] Remote host '{host}' not found")
			raise typer.Exit(1)
		result = run_remote_sentinel(remote, ["list"])
		_print_remote_result(result)
		return

	state = load_state()
	remotes = state.list_remotes()
	if not remotes:
		console.print("[dim]No remote hosts registered[/]")
		return

	table = Table(show_header=True, header_style="bold")
	table.add_column("HOST", style="bold")
	table.add_column("USER")
	table.add_column("PORT")
	table.add_column("CREATED")

	for remote in remotes:
		table.add_row(
			remote.host,
			remote.user or "[dim]-[/]",
			str(remote.port) if remote.port else "[dim]-[/]",
			remote.created_at,
		)

	console.print(table)


@remote_app.command("run")
def remote_run(
	host: Annotated[str, typer.Argument(help="Remote host")],
	command: Annotated[list[str], typer.Argument(help="Command to run remotely")],
) -> None:
	"""Run 'sentinel run <command...>' on a remote host"""
	state = load_state()
	remote = state.get_remote(host)
	if remote is None:
		console.print(f"[red]✗[/] Remote host '{host}' not found")
		raise typer.Exit(1)

	result = run_remote_sentinel(remote, ["run", *command])
	_print_remote_result(result)


@remote_app.command("stop")
def remote_stop(
	host: Annotated[str, typer.Argument(help="Remote host")],
	id_or_name: Annotated[str, typer.Argument(help="Process ID or name on the remote host")],
) -> None:
	"""Stop a process on a remote host"""
	state = load_state()
	remote = state.get_remote(host)
	if remote is None:
		console.print(f"[red]✗[/] Remote host '{host}' not found")
		raise typer.Exit(1)

	result = run_remote_sentinel(remote, ["stop", id_or_name])
	_print_remote_result(result)
