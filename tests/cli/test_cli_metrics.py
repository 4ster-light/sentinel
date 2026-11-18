from collections.abc import Callable
from typing import cast

from typer.testing import CliRunner

from sentinel_cli import app
from sentinel_core.process import start_process
from sentinel_core.state import State

runner = CliRunner()


class _StubMetricsServer:
	def __init__(self) -> None:
		self.server_address = ("127.0.0.1", 9464)
		self.served = False

	def __enter__(self) -> _StubMetricsServer:
		return self

	def __exit__(self, *exc: object) -> None:
		return None

	def serve_forever(self) -> None:
		self.served = True


class TestMetricsCommands:
	def test_metrics_snapshot_empty(self, state: State):
		result = runner.invoke(app, ["metrics", "snapshot"])
		assert result.exit_code == 0
		assert "No processes" in result.stdout or "No processes to report" in result.stdout

	def test_metrics_snapshot_with_process(self, state: State):
		start_process(state, "sleep 10", name="metricproc")
		result = runner.invoke(app, ["metrics", "snapshot"])
		assert result.exit_code == 0
		assert "metricproc" in result.stdout

	def test_metrics_export_json_to_stdout(self, state: State):
		start_process(state, "sleep 10", name="jsonproc")
		result = runner.invoke(app, ["metrics", "export", "--format", "json"])
		assert result.exit_code == 0
		assert '"name": "jsonproc"' in result.stdout

	def test_metrics_export_json_to_file(self, state: State, tmp_path):
		start_process(state, "sleep 10", name="fileproc")
		output = tmp_path / "metrics.json"
		result = runner.invoke(app, ["metrics", "export", "--format", "json", "--output", str(output)])
		assert result.exit_code == 0
		assert output.exists()
		content = output.read_text()
		assert '"name": "fileproc"' in content

	def test_metrics_export_table(self, state: State):
		start_process(state, "sleep 10", name="tableproc")
		result = runner.invoke(app, ["metrics", "export", "--format", "table"])
		assert result.exit_code == 0
		assert "tableproc" in result.stdout

	def test_metrics_export_invalid_format(self, state: State):
		result = runner.invoke(app, ["metrics", "export", "--format", "xml"])
		assert result.exit_code != 0

	def test_metrics_export_table_to_file(self, state: State, tmp_path):
		start_process(state, "sleep 10", name="tablefileproc")
		output = tmp_path / "metrics.txt"
		result = runner.invoke(app, ["metrics", "export", "--format", "table", "--output", str(output)])
		assert result.exit_code == 0
		assert output.exists()
		content = output.read_text()
		assert "tablefileproc" in content
		assert "\x1b" not in content

	def test_metrics_export_prometheus_stdout(self, state: State):
		start_process(state, "sleep 10", name="promproc")
		result = runner.invoke(app, ["metrics", "export", "--format", "prometheus"])

		assert result.exit_code == 0
		assert 'sentinel_process_up{id="1",name="promproc"} 1' in result.stdout
		assert "sentinel_processes_total 1" in result.stdout
		assert "\x1b" not in result.stdout

	def test_metrics_export_prometheus_to_file(self, state: State, tmp_path):
		start_process(state, "sleep 10", name="promfile")
		output = tmp_path / "metrics.prom"
		result = runner.invoke(app, ["metrics", "export", "--format", "prometheus", "--output", str(output)])

		assert result.exit_code == 0
		content = output.read_text(encoding="utf-8")
		assert 'sentinel_process_up{id="1",name="promfile"} 1' in content

	def test_metrics_export_invalid_format_names_prometheus(self, state: State):
		result = runner.invoke(app, ["metrics", "export", "--format", "xml"])

		assert result.exit_code != 0
		assert "prometheus" in result.stderr.lower()

	def test_metrics_serve_rejects_invalid_port(self, state: State):
		result = runner.invoke(app, ["metrics", "serve", "--port", "0"])

		assert result.exit_code != 0
		assert "between 1 and 65535" in result.stdout

	def test_metrics_serve_wires_server_and_renders_metrics(self, state: State, monkeypatch):
		created: dict[str, object] = {}
		server = _StubMetricsServer()

		def fake_create(address: tuple[str, int], render: Callable[[], str]) -> _StubMetricsServer:
			created["address"] = address
			created["render"] = render
			return server

		monkeypatch.setattr("sentinel_cli.metrics.create_metrics_server", fake_create)
		result = runner.invoke(app, ["metrics", "serve", "--port", "9464"])

		assert result.exit_code == 0
		assert server.served is True
		assert created["address"] == ("127.0.0.1", 9464)
		assert "http://127.0.0.1:9464/metrics" in result.stdout
		render = cast(Callable[[], str], created["render"])
		assert "sentinel_processes_total 0" in render()
