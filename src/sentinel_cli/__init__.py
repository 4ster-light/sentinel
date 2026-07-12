"""CLI interface for Sentinel"""

import typer

from .daemon import daemon_app
from .group import group_app
from .main import register_main_commands
from .metrics import metrics_app
from .port import port_app
from .remote import remote_app
from .startup import startup_app

app = typer.Typer(
	name="sentinel",
	help="A lightweight process orchestrator CLI",
	no_args_is_help=True,
)

register_main_commands(app)
app.add_typer(port_app, name="port")
app.add_typer(group_app, name="group")
app.add_typer(daemon_app, name="daemon")
app.add_typer(startup_app, name="startup")
app.add_typer(metrics_app, name="metrics")
app.add_typer(remote_app, name="remote")

__all__ = ["app"]
