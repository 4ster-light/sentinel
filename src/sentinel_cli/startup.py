"""Startup script generation commands"""

import re
from collections.abc import Sequence
from shlex import join as shlex_join
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
		console.print(render_systemd_service(name, command, user=user, cwd=cwd, restart=restart))
	except ValueError as e:
		console.print(f"[red]✗[/] {e}")
		raise typer.Exit(1)


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
		raise typer.Exit(1)

	typer.echo(script, nl=False)
