"""Metrics collection and export utilities"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table
from rich.markup import escape

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
				uptime_seconds=uptime_from_started_at(info.started_at) if status.running else 0,
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
		status_str = "[green]running[/]" if metric.running else f"[red]{metric.status}[/]"
		table.add_row(
			str(metric.id),
			escape(metric.name),
			str(metric.pid),
			status_str,
			f"{metric.cpu_percent:.1f}%",
			format_memory_mb(metric.memory_mb),
			format_uptime_seconds(metric.uptime_seconds),
		)

	output_console.print(table)


PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


def _escape_label_value(value: str) -> str:
	"""Escape a Prometheus label value: backslash, double quote and newline."""
	return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _labels(**labels: str | int) -> str:
	rendered = ",".join(f'{key}="{_escape_label_value(str(value))}"' for key, value in labels.items())
	return "{" + rendered + "}"


def _format_number(value: float) -> str:
	if value == int(value):
		return str(int(value))
	return f"{value:.3f}".rstrip("0").rstrip(".")


def render_prometheus(metrics: Sequence[ProcessMetrics]) -> str:
	"""Render metrics in the Prometheus text exposition format (version 0.0.4)."""
	series = [(metric, _labels(id=metric.id, name=metric.name)) for metric in metrics]
	lines: list[str] = [
		"# HELP sentinel_processes_total Number of processes tracked by Sentinel.",
		"# TYPE sentinel_processes_total gauge",
		f"sentinel_processes_total {len(metrics)}",
		"# HELP sentinel_process_up Whether Sentinel sees the process as running (1) or not (0).",
		"# TYPE sentinel_process_up gauge",
	]
	lines.extend(f"sentinel_process_up{labels} {int(metric.running)}" for metric, labels in series)

	lines.extend(
		[
			"# HELP sentinel_process_cpu_percent CPU usage of the process, in percent.",
			"# TYPE sentinel_process_cpu_percent gauge",
		]
	)
	lines.extend(
		f"sentinel_process_cpu_percent{labels} {_format_number(metric.cpu_percent)}" for metric, labels in series
	)

	lines.extend(
		[
			"# HELP sentinel_process_memory_bytes Resident memory of the process, in bytes.",
			"# TYPE sentinel_process_memory_bytes gauge",
		]
	)
	lines.extend(
		f"sentinel_process_memory_bytes{labels} {round(metric.memory_mb * 1024 * 1024)}" for metric, labels in series
	)

	lines.extend(
		[
			"# HELP sentinel_process_uptime_seconds Seconds since the process started.",
			"# TYPE sentinel_process_uptime_seconds gauge",
		]
	)
	lines.extend(
		f"sentinel_process_uptime_seconds{labels} {_format_number(metric.uptime_seconds)}" for metric, labels in series
	)

	return "\n".join(lines) + "\n"


def export_to_prometheus(metrics: Sequence[ProcessMetrics], path: Path | str) -> None:
	output = Path(path)
	output.write_text(render_prometheus(metrics), encoding="utf-8")
