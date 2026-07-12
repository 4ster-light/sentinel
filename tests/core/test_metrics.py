from datetime import datetime
from pathlib import Path
from unittest.mock import patch


from sentinel_core.metrics import (
	ProcessMetrics,
	collect_metrics,
	export_to_json,
	export_to_stdout,
)
from sentinel_core.state import ProcessInfo, ProcessStatus, State


class TestProcessMetrics:
	def test_to_dict(self):
		metric = ProcessMetrics(
			id=1,
			name="test",
			pid=12345,
			status="running",
			running=True,
			cpu_percent=5.5,
			memory_mb=128.0,
			uptime_seconds=60.0,
		)
		data = metric.to_dict()
		assert data == {
			"id": 1,
			"name": "test",
			"pid": 12345,
			"status": "running",
			"running": True,
			"cpu_percent": 5.5,
			"memory_mb": 128.0,
			"uptime_seconds": 60.0,
		}


class TestCollectMetrics:
	def test_collect_metrics_empty_state(self, state: State):
		metrics = collect_metrics(state)
		assert metrics == []

	def test_collect_metrics_running_process(self, state: State, temp_state_dir: Path):
		info = ProcessInfo(
			id=1,
			pid=12345,
			name="proc",
			cmd="sleep 60",
			cwd="/tmp",
			restart=False,
			started_at=datetime.now().isoformat(),
			stdout_log="/tmp/proc.stdout.log",
			stderr_log="/tmp/proc.stderr.log",
		)
		state.add_process(info)

		with patch("sentinel_core.metrics.get_process_status") as mock_status:
			mock_status.return_value = ProcessStatus(
				running=True,
				status="running",
				cpu_percent=2.5,
				memory_mb=64.0,
			)
			metrics = collect_metrics(state)

		assert len(metrics) == 1
		assert metrics[0].id == 1
		assert metrics[0].name == "proc"
		assert metrics[0].pid == 12345
		assert metrics[0].status == "running"
		assert metrics[0].running is True
		assert metrics[0].cpu_percent == 2.5
		assert metrics[0].memory_mb == 64.0
		assert metrics[0].uptime_seconds >= 0

	def test_collect_metrics_dead_process(self, state: State, temp_state_dir: Path):
		info = ProcessInfo(
			id=1,
			pid=99999,
			name="dead",
			cmd="sleep 60",
			cwd="/tmp",
			restart=False,
			started_at="2024-01-01T00:00:00",
			stdout_log="/tmp/dead.stdout.log",
			stderr_log="/tmp/dead.stderr.log",
		)
		state.add_process(info)

		metrics = collect_metrics(state)

		assert len(metrics) == 1
		assert metrics[0].running is False
		assert metrics[0].status == "exited"
		assert metrics[0].cpu_percent == 0
		assert metrics[0].memory_mb == 0


class TestExportMetrics:
	def test_export_to_json(self, tmp_path: Path):
		metrics = [
			ProcessMetrics(
				id=1,
				name="proc",
				pid=123,
				status="running",
				running=True,
				cpu_percent=1.0,
				memory_mb=32.0,
				uptime_seconds=10.0,
			)
		]
		path = tmp_path / "metrics.json"
		export_to_json(metrics, path)

		content = path.read_text()
		assert '"name": "proc"' in content
		assert '"pid": 123' in content

	def test_export_to_stdout(self, capsys):
		metrics = [
			ProcessMetrics(
				id=1,
				name="proc",
				pid=123,
				status="running",
				running=True,
				cpu_percent=1.0,
				memory_mb=32.0,
				uptime_seconds=10.0,
			)
		]
		export_to_stdout(metrics)

		captured = capsys.readouterr()
		assert "proc" in captured.out
		assert "123" in captured.out
		assert "running" in captured.out

	def test_export_to_stdout_empty(self, capsys):
		export_to_stdout([])

		captured = capsys.readouterr()
		assert "No processes" in captured.out

	def test_export_to_stdout_formats_memory_and_uptime(self, capsys):
		metrics = [
			ProcessMetrics(
				id=1,
				name="tiny",
				pid=1,
				status="running",
				running=True,
				cpu_percent=0.0,
				memory_mb=0.5,
				uptime_seconds=30.0,
			),
			ProcessMetrics(
				id=2,
				name="medium",
				pid=2,
				status="running",
				running=True,
				cpu_percent=0.0,
				memory_mb=128.0,
				uptime_seconds=120.0,
			),
			ProcessMetrics(
				id=3,
				name="hourly",
				pid=3,
				status="running",
				running=True,
				cpu_percent=0.0,
				memory_mb=256.0,
				uptime_seconds=7200.0,
			),
			ProcessMetrics(
				id=4,
				name="big",
				pid=4,
				status="running",
				running=True,
				cpu_percent=0.0,
				memory_mb=2048.0,
				uptime_seconds=90000.0,
			),
		]
		export_to_stdout(metrics)

		captured = capsys.readouterr()
		assert "512KB" in captured.out
		assert "128.0MB" in captured.out
		assert "2m 0s" in captured.out
		assert "2h 0m" in captured.out
		assert "2.00GB" in captured.out
		assert "1d" in captured.out

	def test_collect_metrics_invalid_started_at(self, state: State, temp_state_dir: Path):
		info = ProcessInfo(
			id=1,
			pid=12345,
			name="badtime",
			cmd="sleep 60",
			cwd="/tmp",
			restart=False,
			started_at="not-a-timestamp",
			stdout_log="/tmp/badtime.stdout.log",
			stderr_log="/tmp/badtime.stderr.log",
		)
		state.add_process(info)

		with patch("sentinel_core.metrics.get_process_status") as mock_status:
			mock_status.return_value = ProcessStatus(
				running=True,
				status="running",
				cpu_percent=0.0,
				memory_mb=1.0,
			)
			metrics = collect_metrics(state)

		assert metrics[0].uptime_seconds == 0.0
