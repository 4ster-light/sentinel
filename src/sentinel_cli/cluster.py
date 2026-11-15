"""Cluster management commands"""

from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from sentinel_core.cluster import cluster_members, cluster_spec, scale_cluster
from sentinel_core.models import ProcessInfo
from sentinel_core.process import ProcessIdentityError, managed_process
from .common import load_state

console = Console()
cluster_app = typer.Typer(
	name="cluster",
	help="Process cluster management",
	no_args_is_help=True,
)


def _running(instance: ProcessInfo) -> bool:
	try:
		return managed_process(instance) is not None
	except ProcessIdentityError:
		return False


@cluster_app.command("list")
def cluster_list() -> None:
	"""List clusters, their instance ranges and how many instances are running"""
	state = load_state()
	names = sorted({info.cluster for info in state.list_processes() if info.cluster})

	if not names:
		console.print("[dim]No clusters found[/]")
		return

	table = Table(show_header=True, header_style="bold")
	table.add_column("CLUSTER", style="bold")
	table.add_column("RUNNING", justify="right")
	table.add_column("INSTANCES", justify="right")
	table.add_column("RANGE", justify="right")

	for name in names:
		members = cluster_members(state, name)
		running = sum(1 for member in members if _running(member))
		table.add_row(
			escape(name),
			str(running),
			str(len(members)),
			cluster_spec(members).describe(),
		)

	console.print(table)


@cluster_app.command("scale")
def cluster_scale(
	name: Annotated[str, typer.Argument(help="Cluster name")],
	count: Annotated[int, typer.Argument(help="Desired number of instances")],
	force: Annotated[bool, typer.Option("--force", "-f", help="Force kill scaled-down instances")] = False,
) -> None:
	"""Grow or shrink a cluster within its recorded range"""
	state = load_state()

	try:
		result = scale_cluster(state, name, count, force=force)
	except ValueError as error:
		console.print(f"[red]✗[/] {escape(str(error))}")
		raise typer.Exit(1)

	for info in result.stopped:
		console.print(f"[green]✓[/] Stopped [bold]{escape(info.name)}[/]")
	for info in result.started:
		console.print(f"[green]✓[/] Started [bold]{escape(info.name)}[/] (id: {info.id}, pid: {info.pid})")

	console.print(f"[green]✓[/] Cluster [bold]{escape(name)}[/] now runs {count} instance(s)")
