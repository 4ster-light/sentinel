"""Tests for CLI metrics commands"""

from typer.testing import CliRunner

from sentinel_cli import app
from sentinel_core.process import start_process
from sentinel_core.state import State

runner = CliRunner()


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
