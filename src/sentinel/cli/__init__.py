"""CLI interface for Sentinel"""

import atexit

import typer

from ..restart_monitor import start_restart_monitor, stop_restart_monitor
from .main import register_main_commands
from .port import port_app
from .group import group_app

app = typer.Typer(
	name="sentinel",
	help="A simple process supervisor CLI",
	no_args_is_help=True,
)

register_main_commands(app)
app.add_typer(port_app, name="port")
app.add_typer(group_app, name="group")

# Start the restart monitor when CLI starts
start_restart_monitor()

# Ensure the monitor is stopped when the CLI exits
atexit.register(stop_restart_monitor)

__all__ = ["app"]
