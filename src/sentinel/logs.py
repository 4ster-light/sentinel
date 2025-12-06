"""Log viewing and tailing"""

import time
from pathlib import Path

from rich.console import Console

console = Console()


def tail_file(path: Path, lines: int = 50) -> list[str]:
	"""Get the last N lines from a file"""
	if not path.exists():
		return []

	try:
		content = path.read_text()
		all_lines = content.splitlines()
		return all_lines[-lines:] if len(all_lines) > lines else all_lines
	except Exception:
		return []


def show_logs(
	stdout_path: str,
	stderr_path: str,
	lines: int = 50,
	follow: bool = False,
	stream: str = "both",
) -> None:
	"""Display logs from a process"""
	stdout = Path(stdout_path)
	stderr = Path(stderr_path)

	if stream in ("stdout", "both") and stdout.exists():
		console.print(f"[bold cyan]═══ stdout ({stdout}) ═══[/]")
		for line in tail_file(stdout, lines):
			console.print(line)

	if stream in ("stderr", "both") and stderr.exists():
		console.print(f"\n[bold red]═══ stderr ({stderr}) ═══[/]")
		for line in tail_file(stderr, lines):
			console.print(f"[red]{line}[/]")

	if follow:
		console.print("\n[dim]Following logs (Ctrl+C to stop)...[/]")
		_follow_logs(stdout, stderr, stream)


def _follow_logs(stdout: Path, stderr: Path, stream: str) -> None:
	"""Follow log files in real-time"""
	stdout_pos = stdout.stat().st_size if stdout.exists() else 0
	stderr_pos = stderr.stat().st_size if stderr.exists() else 0

	try:
		while True:
			if stream in ("stdout", "both") and stdout.exists():
				current_size = stdout.stat().st_size
				if current_size > stdout_pos:
					with open(stdout) as f:
						f.seek(stdout_pos)
						new_content = f.read()
						for line in new_content.splitlines():
							console.print(f"[cyan]out:[/] {line}")
					stdout_pos = current_size

			if stream in ("stderr", "both") and stderr.exists():
				current_size = stderr.stat().st_size
				if current_size > stderr_pos:
					with open(stderr) as f:
						f.seek(stderr_pos)
						new_content = f.read()
						for line in new_content.splitlines():
							console.print(f"[red]err:[/] {line}")
					stderr_pos = current_size

			time.sleep(0.5)
	except KeyboardInterrupt:
		console.print("\n[dim]Stopped following logs.[/]")


def clear_logs(stdout_path: str, stderr_path: str) -> None:
	"""Clear log files"""
	for path_str in (stdout_path, stderr_path):
		path = Path(path_str)
		if path.exists():
			path.write_text("")
