"""Port management commands"""

from datetime import datetime
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from ..state import State

console = Console()
port_app = typer.Typer(
	name="port",
	help="Port management commands",
	no_args_is_help=True,
)


@port_app.command("allocate")
def port_allocate(
	port: Annotated[int | None, typer.Argument(help="Specific port to allocate")] = None,
	name: Annotated[str, typer.Option("--name", "-n", help="Name for the allocation")] = "default",
) -> None:
	"""Allocate a port"""
	state = State()
	allocated = state.allocate_port(name, port)

	if allocated:
		console.print(f"[green]✓[/] Allocated port [bold]{allocated}[/] ({name})")
	else:
		console.print("[red]✗[/] Failed to allocate port")
		raise typer.Exit(1)


@port_app.command("free")
def port_free(
	port: Annotated[int, typer.Argument(help="Port to free")],
) -> None:
	"""Free an allocated port"""
	state = State()

	if state.free_port(port):
		console.print(f"[green]✓[/] Freed port [bold]{port}[/]")
	else:
		console.print(f"[red]✗[/] Port {port} not found")
		raise typer.Exit(1)


@port_app.command("list")
def port_list(
	name: Annotated[str | None, typer.Option("--name", "-n", help="Filter by name")] = None,
) -> None:
	"""List allocated ports"""
	state = State()
	ports = state.list_ports(name)

	if not ports:
		console.print("[dim]No ports allocated[/]")
		return

	table = Table(show_header=True, header_style="bold")
	table.add_column("PORT", style="cyan", justify="right")
	table.add_column("NAME", style="bold")
	table.add_column("ALLOCATED")

	for info in sorted(ports, key=lambda p: p.port):
		allocated = datetime.fromisoformat(info.allocated_at)
		table.add_row(
			str(info.port),
			info.name,
			allocated.strftime("%Y-%m-%d %H:%M"),
		)

	console.print(table)
