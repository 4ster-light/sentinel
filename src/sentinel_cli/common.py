"""Shared CLI helpers"""

from rich.console import Console

from sentinel_core.state import State

console = Console()


def load_state() -> State:
	"""Construct the CLI state, surfacing any state-load warnings."""
	state = State()
	for warning in state.load_warnings:
		console.print(f"[red]✗[/] {warning}")
	return state
