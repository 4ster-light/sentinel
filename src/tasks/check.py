"""Task to run code formatting, linting, and type checking."""

from .uv import uv_run, CMD


def main() -> None:
	commands: list[CMD] = [
		CMD(name="Formatting", args=["ruff", "format"]),
		CMD(name="Linting", args=["ruff", "check", "--fix"]),
		CMD(name="Type Checking", args=["ty", "check"]),
	]

	for cmd in commands:
		uv_run(cmd)
