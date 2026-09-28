"""Metrics export commands"""

import json
from typing import Annotated

import typer
from rich.console import Console

from sentinel_core.metrics import collect_metrics, export_to_json, export_to_stdout
from .common import load_state

console = Console()
metrics_app = typer.Typer(name="metrics", help="Export process metrics", no_args_is_help=True)


@metrics_app.command()
def export(
	fmt: Annotated[
		str,
		typer.Option("--format", "-f", help="Output format: json or table"),
	] = "table",
	output: Annotated[
		str | None,
		typer.Option("--output", "-o", help="Path to write metrics to"),
	] = None,
) -> None:
	"""Export process metrics to a file or stdout"""
	if fmt not in ("json", "table"):
		console.print("[red]✗[/] --format must be 'json' or 'table'")
		raise typer.Exit(1)

	state = load_state()
	metrics = collect_metrics(state)

	if output:
		if fmt == "json":
			export_to_json(metrics, output)
		else:
			with open(output, "w") as f:
				file_console = Console(file=f, force_terminal=False, no_color=True, width=console.width)
				export_to_stdout(metrics, output_console=file_console)
		console.print(f"[green]✓[/] Exported metrics to [bold]{output}[/]")
		return

	if fmt == "json":
		console.print(json.dumps([m.to_dict() for m in metrics], indent=2))
	else:
		export_to_stdout(metrics)


@metrics_app.command()
def snapshot() -> None:
	"""Print a one-shot metrics snapshot to stdout"""
	state = load_state()
	metrics = collect_metrics(state)
	export_to_stdout(metrics)
