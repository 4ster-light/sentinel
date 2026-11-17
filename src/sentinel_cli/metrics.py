"""Metrics export commands"""

import json
from typing import Annotated

import typer
from rich.console import Console

from sentinel_core.metrics import (
	collect_metrics,
	export_to_json,
	export_to_prometheus,
	export_to_stdout,
	render_prometheus,
)
from sentinel_core.metrics_server import create_metrics_server

from .common import load_state

console = Console()
metrics_app = typer.Typer(name="metrics", help="Export process metrics", no_args_is_help=True)

METRICS_FORMATS = ("json", "table", "prometheus")


@metrics_app.command()
def export(
	fmt: Annotated[
		str,
		typer.Option("--format", "-f", help="Output format: json, table or prometheus"),
	] = "table",
	output: Annotated[
		str | None,
		typer.Option("--output", "-o", help="Path to write metrics to"),
	] = None,
) -> None:
	"""Export process metrics to a file or stdout"""
	if fmt not in METRICS_FORMATS:
		console.print("[red]✗[/] --format must be 'json', 'table' or 'prometheus'")
		raise typer.Exit(1)

	metrics = collect_metrics(load_state())

	if output:
		if fmt == "json":
			export_to_json(metrics, output)
		elif fmt == "prometheus":
			export_to_prometheus(metrics, output)
		else:
			with open(output, "w", encoding="utf-8") as f:
				file_console = Console(file=f, force_terminal=False, no_color=True, width=console.width)
				export_to_stdout(metrics, output_console=file_console)
		console.print(f"[green]✓[/] Exported metrics to [bold]{output}[/]")
		return

	if fmt == "json":
		console.print(json.dumps([m.to_dict() for m in metrics], indent=2))
	elif fmt == "prometheus":
		typer.echo(render_prometheus(metrics), nl=False)
	else:
		export_to_stdout(metrics)


@metrics_app.command()
def snapshot() -> None:
	"""Print a one-shot metrics snapshot to stdout"""
	export_to_stdout(collect_metrics(load_state()))


@metrics_app.command()
def serve(
	host: Annotated[str, typer.Option("--host", help="Address to bind for scrapes")] = "127.0.0.1",
	port: Annotated[int, typer.Option("--port", "-p", help="Port to bind for scrapes")] = 9464,
) -> None:
	"""Serve metrics at /metrics for Prometheus to scrape"""
	if not 1 <= port <= 65535:
		console.print("[red]✗[/] --port must be between 1 and 65535")
		raise typer.Exit(1)

	def render() -> str:
		return render_prometheus(collect_metrics(load_state()))

	try:
		server = create_metrics_server((host, port), render)
	except OSError as e:
		console.print(f"[red]✗[/] Cannot bind {host}:{port}: {e}")
		raise typer.Exit(1) from e

	bound_host, bound_port = server.server_address[:2]
	console.print(f"[green]✓[/] Serving Prometheus metrics at [bold]http://{bound_host}:{bound_port}/metrics[/]")
	try:
		with server:
			server.serve_forever()
	except KeyboardInterrupt:
		console.print("[dim]Stopped metrics server[/]")
