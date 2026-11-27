"""HTTP endpoint exposing metrics in the Prometheus text format."""

from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast

from .metrics import PROMETHEUS_CONTENT_TYPE

RenderMetrics = Callable[[], str]


class MetricsServer(ThreadingHTTPServer):
	"""Threaded HTTP server that renders metrics on every scrape."""

	daemon_threads = True

	def __init__(self, server_address: tuple[str, int], render: RenderMetrics) -> None:
		super().__init__(server_address, MetricsRequestHandler)
		self.render_metrics = render


class MetricsRequestHandler(BaseHTTPRequestHandler):
	"""Serve rendered metrics at /metrics and 404 for everything else."""

	def do_GET(self) -> None:
		path = self.path.partition("?")[0]
		if path not in ("/metrics", "/metrics/"):
			self.send_error(HTTPStatus.NOT_FOUND, "Only /metrics is available")
			return

		server = cast(MetricsServer, self.server)  # pragma: no mutate (cast is a typing no-op)
		body = server.render_metrics().encode()
		content_type = PROMETHEUS_CONTENT_TYPE
		content_length = str(len(body))
		self.send_response(HTTPStatus.OK)
		self.send_header("Content-Type", content_type)  # pragma: no mutate (case-insensitive header)
		self.send_header("Content-Length", content_length)  # pragma: no mutate (case-insensitive header)
		self.end_headers()
		self.wfile.write(body)

	def log_message(self, format: str, *args: object) -> None:
		"""Stay quiet: Prometheus scrapes every few seconds."""


def create_metrics_server(address: tuple[str, int], render: RenderMetrics) -> MetricsServer:
	"""Bind a metrics server to address without starting its serve loop."""
	return MetricsServer(address, render)
