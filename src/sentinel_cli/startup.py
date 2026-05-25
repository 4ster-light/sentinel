"""Startup script generation commands"""

from collections.abc import Sequence
from shlex import join as shlex_join
from typing import Annotated

import typer
from rich.console import Console

console = Console()
startup_app = typer.Typer(
	name="startup",
	help="Generate startup scripts",
	no_args_is_help=True,
)


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
		raise ValueError("service name cannot be empty")
	if not command:
		raise ValueError("command cannot be empty")

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
			f"ExecStart=/usr/bin/env {shlex_join(list(command))}",
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
		console.print(render_systemd_service(name, command, user=user, cwd=cwd, restart=restart))
	except ValueError as e:
		console.print(f"[red]✗[/] {e}")
		raise typer.Exit(1)
