"""Value tests for the metrics rendering and the format helpers"""

import json
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from rich.console import Console

from sentinel_core import format as fmt
from sentinel_core import metrics
from sentinel_core.models import ProcessInfo, ProcessStatus
from sentinel_core.state import State


def metric(
	name: str = "api",
	ident: int = 7,
	pid: int = 4242,
	status: str = "running",
	running: bool = True,
	cpu: float = 12.5,
	mem: float = 256.0,
	uptime: float = 3661.0,
) -> metrics.ProcessMetrics:
	return metrics.ProcessMetrics(
		id=ident,
		name=name,
		pid=pid,
		status=status,
		running=running,
		cpu_percent=cpu,
		memory_mb=mem,
		uptime_seconds=uptime,
	)


class TestUptimeFromStartedAt:
	def test_reads_a_recent_timestamp(self) -> None:
		started_at = (datetime.now() - timedelta(seconds=60)).isoformat()

		assert fmt.uptime_from_started_at(started_at) == pytest.approx(60, abs=2)

	def test_returns_zero_for_an_unreadable_timestamp(self) -> None:
		assert fmt.uptime_from_started_at("not a date") == 0.0


class TestFormatUptimeSeconds:
	@pytest.mark.parametrize(
		("seconds", "expected"),
		[
			(0, "0s"),
			(59, "59s"),
			(60, "1m 0s"),
			(3599, "59m 59s"),
			(3600, "1h 0m"),
			(86399, "23h 59m"),
			(86400, "1d 0h"),
			(90000, "1d 1h"),
		],
	)
	def test_formats_the_scale(self, seconds: float, expected: str) -> None:
		assert fmt.format_uptime_seconds(seconds) == expected


class TestFormatMemoryMb:
	@pytest.mark.parametrize(
		("mb", "expected"),
		[
			(0.5, "512KB"),
			(0.999, "1023KB"),
			(1, "1.0MB"),
			(1023.9, "1023.9MB"),
			(1024, "1.00GB"),
			(2048, "2.00GB"),
		],
	)
	def test_formats_the_scale(self, mb: float, expected: str) -> None:
		assert fmt.format_memory_mb(mb) == expected


class TestPrometheusLabels:
	def test_escapes_backslash_quote_and_newline(self) -> None:
		assert metrics._escape_label_value('a\\b"c\nd') == 'a\\\\b\\"c\\nd'

	def test_renders_the_labels_in_order(self) -> None:
		assert metrics._labels(id=7, name="api") == '{id="7",name="api"}'

	def test_escapes_label_values(self) -> None:
		assert metrics._labels(name='a"b') == '{name="a\\"b"}'


class TestFormatNumber:
	@pytest.mark.parametrize(
		("value", "expected"),
		[(0, "0"), (1.0, "1"), (1.5, "1.5"), (1.23456, "1.235"), (12.5, "12.5"), (2.0, "2")],
	)
	def test_formats_numbers(self, value: float, expected: str) -> None:
		assert metrics._format_number(value) == expected


class TestRenderPrometheus:
	def test_renders_one_metric(self) -> None:
		expected = """# HELP sentinel_processes_total Number of processes tracked by Sentinel.
# TYPE sentinel_processes_total gauge
sentinel_processes_total 1
# HELP sentinel_process_up Whether Sentinel sees the process as running (1) or not (0).
# TYPE sentinel_process_up gauge
sentinel_process_up{id="7",name="api"} 1
# HELP sentinel_process_cpu_percent CPU usage of the process, in percent.
# TYPE sentinel_process_cpu_percent gauge
sentinel_process_cpu_percent{id="7",name="api"} 12.5
# HELP sentinel_process_memory_bytes Resident memory of the process, in bytes.
# TYPE sentinel_process_memory_bytes gauge
sentinel_process_memory_bytes{id="7",name="api"} 268435456
# HELP sentinel_process_uptime_seconds Seconds since the process started.
# TYPE sentinel_process_uptime_seconds gauge
sentinel_process_uptime_seconds{id="7",name="api"} 3661
"""

		assert metrics.render_prometheus([metric(cpu=12.5, mem=256.0, uptime=3661.0)]) == expected

	def test_renders_no_metrics(self) -> None:
		expected = """# HELP sentinel_processes_total Number of processes tracked by Sentinel.
# TYPE sentinel_processes_total gauge
sentinel_processes_total 0
# HELP sentinel_process_up Whether Sentinel sees the process as running (1) or not (0).
# TYPE sentinel_process_up gauge
# HELP sentinel_process_cpu_percent CPU usage of the process, in percent.
# TYPE sentinel_process_cpu_percent gauge
# HELP sentinel_process_memory_bytes Resident memory of the process, in bytes.
# TYPE sentinel_process_memory_bytes gauge
# HELP sentinel_process_uptime_seconds Seconds since the process started.
# TYPE sentinel_process_uptime_seconds gauge
"""

		assert metrics.render_prometheus([]) == expected

	def test_escapes_the_label(self) -> None:
		text = metrics.render_prometheus([metric(name='a"b')])

		assert 'sentinel_process_up{id="7",name="a\\"b"} 1' in text


class TestExportToStdout:
	def test_prints_the_empty_message(self) -> None:
		out = StringIO()

		metrics.export_to_stdout([], Console(file=out, width=80, height=24))

		assert out.getvalue() == "No processes to report metrics for\n"

	def test_prints_a_table_row(self) -> None:
		out = StringIO()

		metrics.export_to_stdout([metric()], Console(file=out, width=80, height=24))

		text = out.getvalue()
		assert "api" in text
		assert "12.5%" in text
		assert "256.0MB" in text
		assert "1h 1m" in text
		assert "running" in text

	def test_prints_the_stopped_status(self) -> None:
		out = StringIO()

		metrics.export_to_stdout([metric(status="exited", running=False)], Console(file=out, width=80, height=24))

		assert "exited" in out.getvalue()


class TestExportFiles:
	def test_writes_the_json(self, tmp_path: Path) -> None:
		path = tmp_path / "metrics.json"

		metrics.export_to_json([metric()], path)

		assert json.loads(path.read_text()) == [metric().to_dict()]

	def test_writes_the_prometheus_text(self, tmp_path: Path) -> None:
		path = tmp_path / "metrics.prom"

		metrics.export_to_prometheus([metric()], path)

		assert path.read_text() == metrics.render_prometheus([metric()])
		assert metrics.PROMETHEUS_CONTENT_TYPE == "text/plain; version=0.0.4; charset=utf-8"


def process_info(name: str = "api", ident: int = 7) -> ProcessInfo:
	return ProcessInfo(
		id=ident,
		pid=4242,
		name=name,
		cmd="true",
		cwd="/",
		restart=True,
		started_at="2026-01-01T00:00:00",
		stdout_log="",
		stderr_log="",
	)


class TestCollectMetrics:
	def test_maps_the_status_and_the_uptime(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(metrics, "get_process_status", lambda info: ProcessStatus(True, "running", 12.5, 256.0))
		monkeypatch.setattr(metrics, "uptime_from_started_at", lambda value: 100.0)
		subject = cast(State, SimpleNamespace(list_processes=lambda: [process_info()]))

		assert metrics.collect_metrics(subject) == [metric(uptime=100.0)]

	def test_zero_uptime_when_not_running(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setattr(metrics, "get_process_status", lambda info: ProcessStatus(False, "exited", 0.0, 0.0))
		subject = cast(State, SimpleNamespace(list_processes=lambda: [process_info()]))

		result = metrics.collect_metrics(subject)

		assert result[0].running is False
		assert result[0].status == "exited"
		assert result[0].uptime_seconds == 0


def render_table(metrics_list: list[metrics.ProcessMetrics]) -> str:
	out = StringIO()
	metrics.export_to_stdout(metrics_list, Console(file=out, width=60, height=24))
	return out.getvalue()


class TestExportToStdoutTable:
	def test_renders_the_exact_table_for_a_running_process(self) -> None:
		metric = metrics.ProcessMetrics(
			id=1,
			name="api",
			pid=4242,
			status="running",
			running=True,
			cpu_percent=12.5,
			memory_mb=300.0,
			uptime_seconds=90.0,
		)

		assert render_table([metric]) == (
			"┏━━━━┳━━━━━━┳━━━━━━┳━━━━━━━━━┳━━━━━━━┳━━━━━━━━━┳━━━━━━━━┓\n"
			"┃ ID ┃ NAME ┃  PID ┃ STATUS  ┃   CPU ┃     MEM ┃ UPTIME ┃\n"
			"┡━━━━╇━━━━━━╇━━━━━━╇━━━━━━━━━╇━━━━━━━╇━━━━━━━━━╇━━━━━━━━┩\n"
			"│  1 │ api  │ 4242 │ running │ 12.5% │ 300.0MB │ 1m 30s │\n"
			"└────┴──────┴──────┴─────────┴───────┴─────────┴────────┘\n"
		)

	def test_renders_the_exact_table_for_a_stopped_process(self) -> None:
		metric = metrics.ProcessMetrics(
			id=2,
			name="a<b>&c",
			pid=7,
			status="exited",
			running=False,
			cpu_percent=0.0,
			memory_mb=1.5,
			uptime_seconds=0.0,
		)

		assert render_table([metric]) == (
			"┏━━━━┳━━━━━━━━┳━━━━━┳━━━━━━━━┳━━━━━━┳━━━━━━━┳━━━━━━━━┓\n"
			"┃ ID ┃ NAME   ┃ PID ┃ STATUS ┃  CPU ┃   MEM ┃ UPTIME ┃\n"
			"┡━━━━╇━━━━━━━━╇━━━━━╇━━━━━━━━╇━━━━━━╇━━━━━━━╇━━━━━━━━┩\n"
			"│  2 │ a<b>&c │   7 │ exited │ 0.0% │ 1.5MB │     0s │\n"
			"└────┴────────┴─────┴────────┴──────┴───────┴────────┘\n"
		)
