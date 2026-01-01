from dataclasses import dataclass
from subprocess import run
from rich import print


@dataclass
class CMD:
	name: str
	args: list[str]


def uv_run(cmd: CMD) -> None:
	print(f"[cyan][bold][underline]{cmd.name}...[/]")
	run(["uv", "run", *cmd.args], check=True)
	print()
