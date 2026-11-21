"""Web dashboard command"""

import json
from typing import Annotated

import typer
from rich.console import Console

from sentinel_web import DASHBOARD_PAGE, collect_dashboard_data, create_dashboard_server

from .common import load_state

console = Console()

DASHBOARD_PORT = 7331


def dashboard(
	host: Annotated[str, typer.Option("--host", help="Address to bind the dashboard to")] = "127.0.0.1",
	port: Annotated[int, typer.Option("--port", "-p", help="Port to bind the dashboard to")] = DASHBOARD_PORT,
) -> None:
	"""Serve a read-only web dashboard for monitoring managed processes"""
	if not 1 <= port <= 65535:
		console.print("[red]✗[/] --port must be between 1 and 65535")
		raise typer.Exit(1)

	def render_page() -> str:
		return DASHBOARD_PAGE

	def render_data() -> str:
		return json.dumps(collect_dashboard_data(load_state()))

	try:
		server = create_dashboard_server((host, port), render_page, render_data)
	except OSError as e:
		console.print(f"[red]✗[/] Cannot bind {host}:{port}: {e}")
		raise typer.Exit(1) from e

	bound_host, bound_port = server.server_address[:2]
	console.print(f"[green]✓[/] Serving dashboard at [bold]http://{bound_host}:{bound_port}/[/]")
	try:
		with server:
			server.serve_forever()
	except KeyboardInterrupt:
		console.print("[dim]Stopped dashboard server[/]")
