"""HTTP endpoints serving the web dashboard: a monitoring page and process data."""

from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast

RenderDashboard = Callable[[], str]

PAGE_CONTENT_TYPE = "text/html; charset=utf-8"
DATA_CONTENT_TYPE = "application/json"
DATA_PATH = "/api/processes"


class DashboardServer(ThreadingHTTPServer):
	"""Threaded HTTP server that renders the dashboard on every request."""

	daemon_threads = True

	def __init__(
		self,
		server_address: tuple[str, int],
		render_page: RenderDashboard,
		render_data: RenderDashboard,
	) -> None:
		super().__init__(server_address, DashboardRequestHandler)
		self.render_page = render_page
		self.render_data = render_data


class DashboardRequestHandler(BaseHTTPRequestHandler):
	"""Serve the monitoring page at / and process data at /api/processes."""

	def do_GET(self) -> None:
		path = self.path.split("?", 1)[0]
		server = cast(DashboardServer, self.server)
		if path == "/":
			self._respond(PAGE_CONTENT_TYPE, server.render_page())
		elif path in (DATA_PATH, f"{DATA_PATH}/"):
			self._respond(DATA_CONTENT_TYPE, server.render_data())
		else:
			self.send_error(HTTPStatus.NOT_FOUND, "Only / and /api/processes are available")

	def _respond(self, content_type: str, body: str) -> None:
		payload = body.encode("utf-8")
		self.send_response(HTTPStatus.OK)
		self.send_header("Content-Type", content_type)
		self.send_header("Content-Length", str(len(payload)))
		self.end_headers()
		self.wfile.write(payload)

	def log_message(self, format: str, *args: object) -> None:
		"""Stay quiet: the dashboard refreshes every few seconds."""


def create_dashboard_server(
	address: tuple[str, int],
	render_page: RenderDashboard,
	render_data: RenderDashboard,
) -> DashboardServer:
	"""Bind a dashboard server to address without starting its serve loop."""
	return DashboardServer(address, render_page, render_data)
