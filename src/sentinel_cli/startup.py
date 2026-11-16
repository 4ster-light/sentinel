"""Startup script generation commands"""

import re
from collections.abc import Sequence
from shlex import join as shlex_join
from shlex import quote as shlex_quote
from typing import Annotated

import typer
from rich.console import Console

console = Console()
startup_app = typer.Typer(
	name="startup",
	help="Generate startup scripts",
	no_args_is_help=True,
)

SERVICE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _validate_initd_name(name: str) -> str:
	trimmed = name.strip()
	if not trimmed:
		raise ValueError("Service name cannot be empty")
	if not SERVICE_NAME_PATTERN.match(trimmed):
		raise ValueError("Service name may only contain letters, digits, dots, dashes and underscores")
	return trimmed


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


def render_initd_script(
	name: str,
	command: Sequence[str],
	*,
	user: str | None = None,
	cwd: str | None = None,
	pidfile: str | None = None,
	logfile: str | None = None,
) -> str:
	"""Render an LSB-compatible SysV init script."""
	service = _validate_initd_name(name)
	if not command:
		raise ValueError("Command cannot be empty")

	lines: list[str] = [
		"#!/bin/sh",
		"### BEGIN INIT INFO",
		f"# Provides:          {service}",
		"# Required-Start:    $local_fs $network $remote_fs",
		"# Required-Stop:     $local_fs $network $remote_fs",
		"# Default-Start:     2 3 4 5",
		"# Default-Stop:      0 1 6",
		f"# Short-Description: Sentinel process: {service}",
		f"# Description:       Starts and stops {service} under SysV init.",
		"### END INIT INFO",
		"",
		f"NAME={shlex_quote(service)}",
		f"COMMAND={shlex_quote(shlex_join(list(command)))}",
		f"RUNAS={shlex_quote(user or '')}",
		f"WORKDIR={shlex_quote(cwd or '')}",
		f"PIDFILE={shlex_quote(pidfile or f'/run/{service}.pid')}",
		f"LOGFILE={shlex_quote(logfile or f'/var/log/{service}.log')}",
		"",
		"is_running() {",
		'\t[ -f "$PIDFILE" ] || return 1',
		'\tpid=$(cat "$PIDFILE" 2>/dev/null) || return 1',
		'\t[ -n "$pid" ] || return 1',
		'\tkill -0 "$pid" 2>/dev/null',
		"}",
		"",
		"start() {",
		"\tif is_running; then",
		'\t\techo "$NAME is already running (pid $(cat "$PIDFILE"))"',
		"\t\treturn 0",
		"\tfi",
		'\tif [ -n "$WORKDIR" ]; then',
		'\t\tcd "$WORKDIR"',
		"\tfi",
		'\tif [ -n "$RUNAS" ]; then',
		'\t\tsetsid su -s /bin/sh -c "$COMMAND" "$RUNAS" >>"$LOGFILE" 2>&1 &',
		"\telse",
		'\t\tsetsid sh -c "$COMMAND" >>"$LOGFILE" 2>&1 &',
		"\tfi",
		'\techo $! >"$PIDFILE"',
		'\techo "$NAME started (pid $(cat "$PIDFILE"))"',
		"}",
		"",
		"stop() {",
		"\tif ! is_running; then",
		'\t\techo "$NAME is not running"',
		'\t\trm -f "$PIDFILE"',
		"\t\treturn 0",
		"\tfi",
		'\tpid=$(cat "$PIDFILE")',
		'\tkill -TERM "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true',
		"\ti=0",
		'\twhile kill -0 "$pid" 2>/dev/null && [ "$i" -lt 30 ]; do',
		"\t\tsleep 1",
		"\t\ti=$((i + 1))",
		"\tdone",
		'\tif kill -0 "$pid" 2>/dev/null; then',
		'\t\tkill -KILL "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true',
		"\tfi",
		'\trm -f "$PIDFILE"',
		'\techo "$NAME stopped"',
		"}",
		"",
		"status() {",
		"\tif is_running; then",
		'\t\techo "$NAME is running (pid $(cat "$PIDFILE"))"',
		"\t\treturn 0",
		"\tfi",
		'\techo "$NAME is not running"',
		"\treturn 3",
		"}",
		"",
		'case "${1:-}" in',
		"\tstart) start ;;",
		"\tstop) stop ;;",
		"\trestart) stop; start ;;",
		"\tstatus) status ;;",
		'\t*) echo "Usage: $0 {start|stop|restart|status}" >&2; exit 1 ;;',
		"esac",
	]
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


@startup_app.command("initd")
def initd(
	name: Annotated[str, typer.Option("--name", "-n", help="Service name")],
	command: Annotated[list[str], typer.Argument(help="Command to run")],
	user: Annotated[str | None, typer.Option("--user", "-u", help="Run the service as this user")] = None,
	cwd: Annotated[str | None, typer.Option("--cwd", help="Working directory for the service")] = None,
	pidfile: Annotated[str | None, typer.Option("--pidfile", help="PID file path (default: /run/<name>.pid)")] = None,
	logfile: Annotated[
		str | None, typer.Option("--logfile", help="Log file path (default: /var/log/<name>.log)")
	] = None,
) -> None:
	"""Generate an LSB-compatible SysV init script."""
	try:
		script = render_initd_script(name, command, user=user, cwd=cwd, pidfile=pidfile, logfile=logfile)
	except ValueError as e:
		console.print(f"[red]✗[/] {e}")
		raise typer.Exit(1)

	typer.echo(script, nl=False)
