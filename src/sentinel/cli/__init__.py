"""CLI interface for Sentinel"""

import typer

app = typer.Typer(
	name="sentinel",
	help="A simple process supervisor CLI",
	no_args_is_help=True,
)

# Import and register command groups after app creation to avoid circular imports
from .main import register_main_commands
from .port import port_app
from .group import group_app

register_main_commands(app)
app.add_typer(port_app, name="port")
app.add_typer(group_app, name="group")

__all__ = ["app"]
