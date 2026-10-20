"""Startup script generation commands"""

from collections.abc import Sequence
import re
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape

console = Console()
startup_app = typer.Typer(
	name="startup",
	help="Generate startup scripts",
	no_args_is_help=True,
)


def _systemd_argument(value: str) -> str:
	# systemd uses its own quoting and expands both specifiers and variables.
	value = value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%").replace("$", "$$")
	return value if re.fullmatch(r"[A-Za-z0-9_./:=+-]+", value) else f'"{value}"'


def render_systemd_service(
	name: str,
	command: Sequence[str],
	*,
	user: str | None = None,
	cwd: str | None = None,
	restart: bool = False,
) -> str:
	"""Render a minimal systemd service unit."""
	if not name.strip():
		raise ValueError("Service name cannot be empty")
	if not command:
		raise ValueError("Command cannot be empty")

	if any(char in value for value in [name, user or "", cwd or "", *command] for char in "\n\r\0"):
		raise ValueError("Unit fields and arguments cannot contain newlines or NUL bytes")
	name = name.replace("%", "%%")
	user = user.replace("%", "%%") if user else None
	cwd = cwd.replace("%", "%%") if cwd else None
	arguments = " ".join(_systemd_argument(arg) for arg in command)
	lines: list[str] = [
		"[Unit]",
		f"Description=Sentinel process: {name}",
		"After=network.target",
		"",
		"[Service]",
		"Type=simple",
	]

	if cwd:
		lines.append(f"WorkingDirectory={cwd}")
	if user:
		lines.append(f"User={user}")

	lines.extend(
		[
			f"ExecStart=/usr/bin/env {arguments}",
			f"Restart={'always' if restart else 'no'}",
			"",
			"[Install]",
			"WantedBy=multi-user.target",
		]
	)
	return "\n".join(lines) + "\n"


@startup_app.command("systemd")
def systemd(
	name: Annotated[str, typer.Option("--name", "-n", help="Service name")],
	command: Annotated[list[str], typer.Argument(help="Command to run")],
	user: Annotated[str | None, typer.Option("--user", "-u", help="Run service as this user")] = None,
	cwd: Annotated[str | None, typer.Option("--cwd", help="Working directory for the service")] = None,
	restart: Annotated[bool, typer.Option("--restart", "-r", help="Always restart the service on exit")] = False,
) -> None:
	"""Generate a minimal systemd service unit."""
	try:
		typer.echo(render_systemd_service(name, command, user=user, cwd=cwd, restart=restart), nl=False)
	except ValueError as e:
		console.print(f"[red]✗[/] {escape(str(e))}")
		raise typer.Exit(1)
