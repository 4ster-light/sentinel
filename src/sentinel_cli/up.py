"""The up command: start a stack from a configuration file"""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape

from sentinel_core.config import discover_config, load_config, run_up
from sentinel_core.process import ProcessIdentityError, managed_process
from sentinel_core.state import State

from .common import load_state

console = Console()
error_console = Console(stderr=True)


def up(
	config: Annotated[
		Path | None,
		typer.Option(
			"--config",
			"-c",
			help="Configuration file; sentinel.toml, sentinel.yaml and sentinel.yml are discovered when omitted",
		),
	] = None,
) -> None:
	"""Start the processes from a configuration file"""
	path = config or discover_config()
	if path is None:
		error_console.print("[red]✗[/] No configuration file found; pass --config FILE")
		raise typer.Exit(1)

	try:
		specs = load_config(path)
		state = load_state()
		report = run_up(state, path, specs)
	except ValueError as e:
		error_console.print(f"[red]✗[/] {escape(str(e))}")
		raise typer.Exit(1) from None

	for group in report.groups_created:
		console.print(f"[green]✓[/] Created group [bold]{escape(group)}[/]")
	for info in report.started:
		console.print(f"[green]✓[/] Started [bold]{escape(info.name)}[/] (id: {info.id}, pid: {info.pid})")
	for name in report.skipped_running:
		console.print(f"[green]✓[/] [bold]{escape(name)}[/] already running")
	for name, recorded in report.conflicts:
		console.print(
			f"[yellow]⚠[/] [bold]{escape(name)}[/] is already recorded with a different command: {escape(recorded)}"
		)
	for name, error in report.failed:
		error_console.print(f"[red]✗[/] Failed to start [bold]{escape(name)}[/]: {escape(error)}")

	not_running = _not_running(state, report.expected)
	if report.failed or not_running:
		for name in not_running:
			error_console.print(f"[red]✗[/] [bold]{escape(name)}[/] is not running")
		raise typer.Exit(1)


def _not_running(state: State, expected: list[str]) -> list[str]:
	"""Names from *expected* that are not confirmed running in *state*."""
	not_running: list[str] = []
	for name in expected:
		info = state.find_process_by_name(name)
		if info is None or info.stopped:
			not_running.append(name)
			continue
		try:
			alive = managed_process(info) is not None
		except ProcessIdentityError:
			alive = False
		if not alive:
			not_running.append(name)
	return not_running
