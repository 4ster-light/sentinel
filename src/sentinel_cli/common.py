"""Shared CLI helpers"""

from rich.console import Console
from rich.markup import escape

from sentinel_core.state import State

console = Console(stderr=True)


def load_state() -> State:
	"""Construct the CLI state, surfacing any state-load warnings."""
	state = State()
	for warning in state.load_warnings:
		console.print(f"[red]✗[/] {escape(warning)}")
	return state
