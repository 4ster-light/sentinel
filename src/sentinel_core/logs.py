"""Log viewing and tailing"""

import os
import shutil
import time
from collections import deque
from pathlib import Path

from rich.console import Console
from rich.markup import escape

console = Console()

DEFAULT_LOG_ROTATION_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_LOG_ROTATION_BACKUPS = 3


def rotate_log_file(
	path: Path, max_bytes: int = DEFAULT_LOG_ROTATION_MAX_BYTES, backups: int = DEFAULT_LOG_ROTATION_BACKUPS
) -> bool:
	if max_bytes <= 0:
		raise ValueError("max_bytes must be greater than 0")
	if backups < 1:
		raise ValueError("backups must be at least 1")
	if not path.exists() or path.stat().st_size < max_bytes:
		return False

	oldest_backup_path = path.with_name(f"{path.name}.{backups}")
	oldest_backup_path.unlink(missing_ok=True)

	for backup_index in range(backups - 1, 0, -1):
		current_backup_path = path.with_name(f"{path.name}.{backup_index}")
		next_backup_path = path.with_name(f"{path.name}.{backup_index + 1}")
		if current_backup_path.exists():
			current_backup_path.replace(next_backup_path)

	first_backup_path = path.with_name(f"{path.name}.1")
	# Keep the inode: running children still hold append descriptors to this file.
	shutil.copy2(path, first_backup_path)
	with path.open("r+b") as active:
		active.truncate(0)
	return True


def rotate_process_logs(
	stdout_path: str,
	stderr_path: str,
	max_bytes: int = DEFAULT_LOG_ROTATION_MAX_BYTES,
	backups: int = DEFAULT_LOG_ROTATION_BACKUPS,
) -> tuple[bool, bool]:
	stdout_rotated = rotate_log_file(Path(stdout_path), max_bytes=max_bytes, backups=backups)
	stderr_rotated = rotate_log_file(Path(stderr_path), max_bytes=max_bytes, backups=backups)
	return stdout_rotated, stderr_rotated


def tail_file(path: Path, lines: int = 50) -> list[str]:
	"""Get the last N lines from a file"""
	if lines <= 0:
		return []
	try:
		with path.open(encoding="utf-8", errors="replace") as stream:
			return [line.rstrip("\r\n") for line in deque(stream, maxlen=lines)]
	except OSError:
		return []


def show_logs(
	stdout_path: str,
	stderr_path: str,
	lines: int = 50,
	follow: bool = False,
	stream: str = "both",
) -> None:
	"""Display logs from a process"""
	if stream not in ("stdout", "stderr", "both"):
		raise ValueError("stream must be stdout, stderr, or both")
	if lines < 0:
		raise ValueError("lines must be non-negative")
	stdout = Path(stdout_path)
	stderr = Path(stderr_path)

	if stream in ("stdout", "both") and stdout.exists():
		console.print(f"[bold cyan]═══ stdout ({escape(str(stdout))}) ═══[/]")
		for line in tail_file(stdout, lines):
			console.print(line, markup=False, highlight=False)

	if stream in ("stderr", "both") and stderr.exists():
		console.print(f"\n[bold red]═══ stderr ({escape(str(stderr))}) ═══[/]")
		for line in tail_file(stderr, lines):
			console.print(line, style="red", markup=False, highlight=False)

	if follow:
		console.print("\n[dim]Following logs (Ctrl+C to stop)...[/]")
		_follow_logs(stdout, stderr, stream)


def _follow_logs(stdout: Path, stderr: Path, stream: str) -> None:
	"""Follow complete lines, reopening files that have been replaced or truncated."""
	paths = [(stdout, "out", "cyan"), (stderr, "err", "red")]
	positions: dict[Path, tuple[int, int, int]] = {}
	pending: dict[Path, bytes] = {}
	for path, _, _ in paths:
		try:
			stat = path.stat()
			positions[path] = (stat.st_dev, stat.st_ino, stat.st_size)
		except FileNotFoundError:
			pass
	try:
		while True:
			for path, label, color in paths:
				if stream != "both" and stream != ("stdout" if label == "out" else "stderr"):
					continue
				try:
					with path.open("rb") as log:
						stat = os.fstat(log.fileno())
						device, inode, offset = positions.get(path, (stat.st_dev, stat.st_ino, 0))
						if (device, inode) != (stat.st_dev, stat.st_ino) or stat.st_size < offset:
							offset = 0
							pending[path] = b""
						log.seek(offset)
						content = pending.get(path, b"") + log.read(65536)
						positions[path] = (stat.st_dev, stat.st_ino, log.tell())
						parts = content.split(b"\n")
						pending[path] = parts.pop()
						for line in parts:
							text = line.rstrip(b"\r").decode("utf-8", errors="replace")
							console.print(f"{label}: {text}", style=color, markup=False, highlight=False)
				except FileNotFoundError:
					continue
			time.sleep(0.5)
	except KeyboardInterrupt:
		console.print("\n[dim]Stopped following logs.[/]")


def clear_logs(stdout_path: str, stderr_path: str) -> None:
	"""Clear log files"""
	for path_str in (stdout_path, stderr_path):
		path = Path(path_str)
		if path.exists():
			path.write_text("")
