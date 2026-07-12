"""Metrics collection and export utilities"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from .process import get_process_status
from .state import State

console = Console()


@dataclass
class ProcessMetrics:
	id: int
	name: str
	pid: int
	status: str
	running: bool
	cpu_percent: float
	memory_mb: float
	uptime_seconds: float

	def to_dict(self) -> dict[str, Any]:
		return {
			"id": self.id,
			"name": self.name,
			"pid": self.pid,
			"status": self.status,
			"running": self.running,
			"cpu_percent": self.cpu_percent,
			"memory_mb": self.memory_mb,
			"uptime_seconds": self.uptime_seconds,
		}


def _calculate_uptime_seconds(started_at: str) -> float:
	try:
		start = datetime.fromisoformat(started_at)
		return (datetime.now() - start).total_seconds()
	except ValueError:
		return 0.0


def collect_metrics(state: State) -> list[ProcessMetrics]:
	metrics: list[ProcessMetrics] = []
	for info in state.list_processes():
		status = get_process_status(info)
		metrics.append(
			ProcessMetrics(
				id=info.id,
				name=info.name,
				pid=info.pid,
				status=status.status,
				running=status.running,
				cpu_percent=status.cpu_percent,
				memory_mb=status.memory_mb,
				uptime_seconds=_calculate_uptime_seconds(info.started_at),
			)
		)
	return metrics


def export_to_json(metrics: list[ProcessMetrics], path: Path | str) -> None:
	output = Path(path)
	output.write_text(json.dumps([m.to_dict() for m in metrics], indent=2))


def _format_uptime(seconds: float) -> str:
	secs = int(seconds)
	if secs < 60:
		return f"{secs}s"
	if secs < 3600:
		return f"{secs // 60}m {secs % 60}s"
	if secs < 86400:
		return f"{secs // 3600}h {(secs % 3600) // 60}m"
	return f"{secs // 86400}d {(secs % 86400) // 3600}h"


def _format_memory(mb: float) -> str:
	if mb < 1:
		return f"{mb * 1024:.0f}KB"
	if mb < 1024:
		return f"{mb:.1f}MB"
	return f"{mb / 1024:.2f}GB"


def export_to_stdout(metrics: list[ProcessMetrics], output_console: Console | None = None) -> None:
	output_console = output_console or console
	if not metrics:
		output_console.print("[dim]No processes to report metrics for[/]")
		return

	table = Table(show_header=True, header_style="bold")
	table.add_column("ID", style="cyan", justify="right")
	table.add_column("NAME", style="bold")
	table.add_column("PID", justify="right")
	table.add_column("STATUS")
	table.add_column("CPU", justify="right")
	table.add_column("MEM", justify="right")
	table.add_column("UPTIME", justify="right")

	for metric in metrics:
		status_str = "[green]running[/]" if metric.running else "[red]stopped[/]"
		table.add_row(
			str(metric.id),
			metric.name,
			str(metric.pid),
			status_str,
			f"{metric.cpu_percent:.1f}%",
			_format_memory(metric.memory_mb),
			_format_uptime(metric.uptime_seconds),
		)

	output_console.print(table)
