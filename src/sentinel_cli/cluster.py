"""Cluster management commands"""

from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from sentinel_core.cluster import cluster_members, cluster_spec, scale_cluster
from sentinel_core.models import ProcessInfo
from sentinel_core.options import parse_autoscale_specs
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
	table.add_column("POLICY")

	for name in names:
		members = cluster_members(state, name)
		running = sum(1 for member in members if _running(member))
		config = next((member.autoscale for member in members if member.autoscale is not None), None)
		table.add_row(
			escape(name),
			str(running),
			str(len(members)),
			cluster_spec(members).describe(),
			escape(config.describe()) if config else "[dim]-[/]",
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
		raise typer.Exit(1) from None

	for info in result.stopped:
		console.print(f"[green]✓[/] Stopped [bold]{escape(info.name)}[/]")
	for info in result.started:
		console.print(f"[green]✓[/] Started [bold]{escape(info.name)}[/] (id: {info.id}, pid: {info.pid})")

	console.print(f"[green]✓[/] Cluster [bold]{escape(name)}[/] now runs {count} instance(s)")


@cluster_app.command("autoscale")
def cluster_autoscale(
	name: Annotated[str, typer.Argument(help="Cluster name")],
	cpu: Annotated[str | None, typer.Option("--cpu", help="CPU thresholds HIGH:LOW in percent")] = None,
	mem: Annotated[str | None, typer.Option("--mem", help="Memory thresholds HIGH:LOW in MB")] = None,
	metric: Annotated[str | None, typer.Option("--metric", help="Metric file thresholds PATH:HIGH:LOW")] = None,
	cooldown: Annotated[float | None, typer.Option("--cooldown", help="Seconds between adjustments")] = None,
	step: Annotated[int | None, typer.Option("--step", help="Instances moved per adjustment")] = None,
	clear: Annotated[bool, typer.Option("--clear", help="Remove the scaling policy")] = False,
) -> None:
	"""Set or clear the scaling policy of a cluster"""
	state = load_state()
	members = cluster_members(state, name)
	if not members:
		console.print(f"[red]✗[/] Unknown cluster [bold]{escape(name)}[/]")
		raise typer.Exit(1)

	if clear:
		if cpu or mem or metric or cooldown is not None or step is not None:
			console.print("[red]✗[/] --clear cannot be combined with --cpu, --mem, --metric, --cooldown or --step")
			raise typer.Exit(1)
		for member in members:
			if member.autoscale is not None:
				member.autoscale = None
				state.add_process(member)
		console.print(f"[green]✓[/] Cleared autoscaling for [bold]{escape(name)}[/]")
		return

	if not cpu and not mem and not metric:
		console.print("[red]✗[/] Provide --cpu HIGH:LOW, --mem HIGH:LOW or --metric PATH:HIGH:LOW, or --clear")
		raise typer.Exit(1)

	if cooldown is not None and cooldown <= 0:
		console.print("[red]✗[/] --cooldown must be greater than 0")
		raise typer.Exit(1)
	if step is not None and step < 1:
		console.print("[red]✗[/] --step must be at least 1")
		raise typer.Exit(1)

	specs: list[str] = []
	if cpu:
		specs.append(f"cpu:{cpu}")
	if mem:
		specs.append(f"mem:{mem}")
	if metric:
		specs.append(f"metric:{metric}")
	try:
		config = parse_autoscale_specs(specs)
		spec = cluster_spec(members)
		if spec.min_instances == spec.max_instances:
			raise ValueError(f"Cluster '{name}' has a fixed size ({spec.describe()}); autoscaling needs a range")
	except ValueError as error:
		console.print(f"[red]✗[/] {escape(str(error))}")
		raise typer.Exit(1) from None

	if cooldown is not None:
		config.cooldown_seconds = cooldown
	if step is not None:
		config.step = step

	for member in members:
		member.autoscale = config
		state.add_process(member)

	console.print(f"[green]✓[/] Cluster [bold]{escape(name)}[/] now scales on {escape(config.describe())}")
	console.print("[dim]  Adjustments happen in the daemon; run 'sentinel daemon start' if it is not running.[/]")
