"""Web dashboard command"""

import socket
from typing import Annotated

import typer
import uvicorn
from rich.console import Console

from sentinel_web import create_dashboard_app

from .common import load_state

console = Console()

DASHBOARD_PORT = 7331


def _check_bind(host: str, port: int) -> None:
	"""Fail early with a readable message if the address cannot be bound."""
	try:
		with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
			probe.bind((host, port))
	except OSError as e:
		console.print(f"[red]✗[/] Cannot bind {host}:{port}: {e}")
		raise typer.Exit(1) from e


def dashboard(
	host: Annotated[str, typer.Option("--host", help="Address to bind the dashboard to")] = "127.0.0.1",
	port: Annotated[int, typer.Option("--port", "-p", help="Port to bind the dashboard to")] = DASHBOARD_PORT,
) -> None:
	"""Serve a read-only web dashboard for monitoring managed processes"""
	if not 1 <= port <= 65535:
		console.print("[red]✗[/] --port must be between 1 and 65535")
		raise typer.Exit(1)

	_check_bind(host, port)
	app = create_dashboard_app(load_state)
	console.print(f"[green]✓[/] Serving dashboard at [bold]http://{host}:{port}/[/]")
	uvicorn.run(app, host=host, port=port, log_level="warning")
	console.print("[dim]Stopped dashboard server[/]")
