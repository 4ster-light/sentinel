"""HTTP endpoint exposing metrics in the Prometheus text format."""

from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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

	server: MetricsServer

	def do_GET(self) -> None:
		if self.path.split("?", 1)[0] not in ("/metrics", "/metrics/"):
			self.send_error(HTTPStatus.NOT_FOUND, "Only /metrics is available")
			return

		body = self.server.render_metrics().encode("utf-8")
		self.send_response(HTTPStatus.OK)
		self.send_header("Content-Type", PROMETHEUS_CONTENT_TYPE)
		self.send_header("Content-Length", str(len(body)))
		self.end_headers()
		self.wfile.write(body)

	def log_message(self, format: str, *args: object) -> None:
		"""Stay quiet: Prometheus scrapes every few seconds."""


def create_metrics_server(address: tuple[str, int], render: RenderMetrics) -> MetricsServer:
	"""Bind a metrics server to address without starting its serve loop."""
	return MetricsServer(address, render)
