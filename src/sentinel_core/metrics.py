"""Metrics collection and export utilities"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from .format import format_memory_mb, format_uptime_seconds, uptime_from_started_at
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
				uptime_seconds=uptime_from_started_at(info.started_at),
			)
		)
	return metrics


def export_to_json(metrics: list[ProcessMetrics], path: Path | str) -> None:
	output = Path(path)
	output.write_text(json.dumps([m.to_dict() for m in metrics], indent=2))


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
			format_memory_mb(metric.memory_mb),
			format_uptime_seconds(metric.uptime_seconds),
		)

	output_console.print(table)
