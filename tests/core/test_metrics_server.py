"""Tests for the Prometheus scrape endpoint"""

import threading
from collections.abc import Iterator
from http.client import HTTPConnection
from typing import cast

import pytest

from sentinel_core.metrics import PROMETHEUS_CONTENT_TYPE
from sentinel_core.metrics_server import MetricsServer, create_metrics_server


def request(server: MetricsServer, path: str) -> tuple[int, str | None, str]:
	host, port = cast(tuple[str, int], server.server_address)[:2]
	connection = HTTPConnection(host, port, timeout=5)
	try:
		connection.request("GET", path)
		response = connection.getresponse()
		return response.status, response.getheader("Content-Type"), response.read().decode("utf-8")
	finally:
		connection.close()


@pytest.fixture
def server() -> Iterator[MetricsServer]:
	body = "# HELP sample A sample.\n# TYPE sample gauge\nsample 1\n"
	try:
		created = create_metrics_server(("127.0.0.1", 0), lambda: body)
	except OSError as e:
		pytest.skip(f"socket creation is unavailable: {e}")
	thread = threading.Thread(target=created.serve_forever, daemon=True)
	thread.start()
	try:
		yield created
	finally:
		created.shutdown()
		created.server_close()
		thread.join(timeout=5)


class TestMetricsServer:
	def test_serves_metrics_with_exposition_content_type(self, server: MetricsServer) -> None:
		status, content_type, body = request(server, "/metrics")

		assert status == 200
		assert content_type == PROMETHEUS_CONTENT_TYPE
		assert body == "# HELP sample A sample.\n# TYPE sample gauge\nsample 1\n"

	def test_metrics_path_accepts_trailing_slash_and_query_string(self, server: MetricsServer) -> None:
		assert request(server, "/metrics/")[0] == 200
		assert request(server, "/metrics?format=prometheus")[0] == 200

	def test_unknown_path_returns_404(self, server: MetricsServer) -> None:
		status, _, _ = request(server, "/health")

		assert status == 404

	def test_render_runs_on_every_scrape(self) -> None:
		calls: list[int] = []

		def render() -> str:
			calls.append(1)
			return f"sentinel_scrapes_total {len(calls)}\n"

		try:
			created = create_metrics_server(("127.0.0.1", 0), render)
		except OSError as e:
			pytest.skip(f"socket creation is unavailable: {e}")
		thread = threading.Thread(target=created.serve_forever, daemon=True)
		thread.start()
		try:
			first = request(created, "/metrics")[2]
			second = request(created, "/metrics")[2]
		finally:
			created.shutdown()
			created.server_close()
			thread.join(timeout=5)

		assert first == "sentinel_scrapes_total 1\n"
		assert second == "sentinel_scrapes_total 2\n"
