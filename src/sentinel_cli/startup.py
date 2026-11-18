"""Startup script generation commands"""

import re
from collections.abc import Sequence
from shlex import join as shlex_join
from shlex import quote as shlex_quote
from subprocess import list2cmdline
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


def _validate_service_name(name: str) -> str:
	trimmed = name.strip()
	if not trimmed:
		raise ValueError("Service name cannot be empty")
	if not SERVICE_NAME_PATTERN.match(trimmed):
		raise ValueError("Service name may only contain letters, digits, dots, dashes and underscores")
	return trimmed


def _powershell_quote(value: str) -> str:
	return "'" + value.replace("'", "''") + "'"


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
	service = _validate_service_name(name)
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


def render_windows_service_script(
	name: str,
	command: Sequence[str],
	*,
	user: str | None = None,
	cwd: str | None = None,
	restart: bool = False,
) -> str:
	"""Render a PowerShell script that installs the command as a Windows service through NSSM."""
	service = _validate_service_name(name)
	if not command:
		raise ValueError("Command cannot be empty")

	application = str(command[0])
	arguments = list2cmdline(list(command[1:]))
	service_name = f"sentinel-{service}"

	lines: list[str] = [
		"#Requires -RunAsAdministrator",
		f"# Installs {service_name} as a Windows service through NSSM; pass -Uninstall to remove it.",
		"param(",
		'\t[string]$NssmPath = "nssm.exe",',
		"\t[switch]$Uninstall",
		")",
		"",
		'$ErrorActionPreference = "Stop"',
		"",
		f"$ServiceName = {_powershell_quote(service_name)}",
		f"$DisplayName = {_powershell_quote(f'Sentinel process: {service}')}",
		f"$Application = {_powershell_quote(application)}",
		f"$Arguments = {_powershell_quote(arguments)}",
	]
	lines.append(f"$WorkingDirectory = {_powershell_quote(cwd)}" if cwd else "$WorkingDirectory = (Get-Location).Path")
	lines.extend(
		[
			"",
			"if (-not (Get-Command $NssmPath -ErrorAction SilentlyContinue)) {",
			'\tthrow "NSSM was not found; install it or pass -NssmPath"',
			"}",
			"",
			"if ($Uninstall) {",
			"\t& $NssmPath stop $ServiceName 2>$null",
			"\t& $NssmPath remove $ServiceName confirm",
			'\tWrite-Host "Removed $ServiceName"',
			"\texit 0",
			"}",
			"",
			"& $NssmPath install $ServiceName",
			"& $NssmPath set $ServiceName Application $Application",
			"& $NssmPath set $ServiceName AppParameters $Arguments",
			"& $NssmPath set $ServiceName AppDirectory $WorkingDirectory",
			"& $NssmPath set $ServiceName DisplayName $DisplayName",
			"& $NssmPath set $ServiceName Start SERVICE_AUTO_START",
		]
	)
	if user:
		lines.extend(
			[
				"",
				f"$Credential = Get-Credential -UserName {_powershell_quote(user)} -Message 'Account for the service'",
				"& $NssmPath set $ServiceName ObjectName $Credential.UserName $Credential.GetNetworkCredential().Password",
			]
		)
	if restart:
		lines.extend(
			[
				"",
				"& $NssmPath set $ServiceName AppExit Default Restart",
				"& $NssmPath set $ServiceName AppRestartDelay 5000",
			]
		)
	lines.extend(
		[
			"",
			"& $NssmPath start $ServiceName",
			'Write-Host "Installed $ServiceName"',
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
		console.print(f"[red]✗[/] {e}")
		raise typer.Exit(1) from None


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
		raise typer.Exit(1) from None

	typer.echo(script, nl=False)


@startup_app.command("windows")
def windows(
	name: Annotated[str, typer.Option("--name", "-n", help="Service name")],
	command: Annotated[list[str], typer.Argument(help="Command to run")],
	user: Annotated[str | None, typer.Option("--user", "-u", help="Run the service as this user")] = None,
	cwd: Annotated[str | None, typer.Option("--cwd", help="Working directory for the service")] = None,
	restart: Annotated[bool, typer.Option("--restart", "-r", help="Restart the service when it exits")] = False,
) -> None:
	"""Generate a PowerShell script that installs the command as a Windows service."""
	try:
		script = render_windows_service_script(name, command, user=user, cwd=cwd, restart=restart)
	except ValueError as e:
		console.print(f"[red]✗[/] {e}")
		raise typer.Exit(1) from None

	typer.echo(script, nl=False)
