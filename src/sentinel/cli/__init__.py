"""CLI interface for Sentinel"""

import typer

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

__all__ = ["app"]
