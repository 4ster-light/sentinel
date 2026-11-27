"""Tests for the metrics HTTP server"""

import http.client
import threading
from collections.abc import Iterator

import pytest

from sentinel_core.metrics import PROMETHEUS_CONTENT_TYPE
from sentinel_core.metrics_server import MetricsServer, create_metrics_server

BODY = "# HELP sentinel_up 1\n# TYPE sentinel_up gauge\nsentinel_up 1\n"


def request(server: MetricsServer, path: str) -> tuple[int, dict[str, str], bytes]:
	host = str(server.server_address[0])
	port = int(server.server_address[1])
	connection = http.client.HTTPConnection(host, port, timeout=10)
	try:
		connection.request("GET", path)
		response = connection.getresponse()
		headers = {name.lower(): value for name, value in response.getheaders()}
		return response.status, headers, response.read()
	finally:
		connection.close()


@pytest.fixture
def server() -> Iterator[MetricsServer]:
	metrics = create_metrics_server(("127.0.0.1", 0), lambda: BODY)
	thread = threading.Thread(target=metrics.serve_forever, daemon=True)
	thread.start()
	try:
		yield metrics
	finally:
		metrics.shutdown()
		metrics.server_close()


class TestMetricsServer:
	def test_serves_rendered_metrics(self, server: MetricsServer) -> None:
		status, headers, body = request(server, "/metrics")

		assert status == 200
		assert headers["content-type"] == PROMETHEUS_CONTENT_TYPE
		assert headers["content-length"] == str(len(body))
		assert body == BODY.encode("utf-8")

	def test_serves_trailing_slash(self, server: MetricsServer) -> None:
		assert request(server, "/metrics/")[0] == 200

	def test_ignores_query_string(self, server: MetricsServer) -> None:
		status, _, body = request(server, "/metrics?format=prometheus")

		assert status == 200
		assert body == BODY.encode("utf-8")

	def test_rejects_other_paths(self, server: MetricsServer) -> None:
		status, _, body = request(server, "/health")

		assert status == 404
		assert b"<p>Message: Only /metrics is available.</p>" in body

	def test_is_threaded_and_daemonic(self, server: MetricsServer) -> None:
		assert server.daemon_threads is True

	def test_renders_on_every_scrape(self) -> None:
		calls: list[int] = []
		metrics = create_metrics_server(("127.0.0.1", 0), lambda: calls.append(1) or BODY)
		thread = threading.Thread(target=metrics.serve_forever, daemon=True)
		thread.start()
		try:
			request(metrics, "/metrics")
			request(metrics, "/metrics")
		finally:
			metrics.shutdown()
			metrics.server_close()

		assert calls == [1, 1]
