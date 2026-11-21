"""Tests for the dashboard HTTP endpoints"""

import json
import threading
from collections.abc import Iterator
from http.client import HTTPConnection
from typing import cast

import pytest

from sentinel_web.server import (
	DATA_CONTENT_TYPE,
	DATA_PATH,
	PAGE_CONTENT_TYPE,
	DashboardServer,
	create_dashboard_server,
)


def request(server: DashboardServer, path: str) -> tuple[int, str | None, str]:
	host, port = cast(tuple[str, int], server.server_address)[:2]
	connection = HTTPConnection(host, port, timeout=5)
	try:
		connection.request("GET", path)
		response = connection.getresponse()
		return response.status, response.getheader("Content-Type"), response.read().decode("utf-8")
	finally:
		connection.close()


def serve(server: DashboardServer) -> threading.Thread:
	thread = threading.Thread(target=server.serve_forever, daemon=True)
	thread.start()
	return thread


@pytest.fixture
def server() -> Iterator[DashboardServer]:
	page_calls: list[str] = []
	data_calls: list[str] = []

	def render_page() -> str:
		page_calls.append("page")
		return f"<html>visits {len(page_calls)}</html>"

	def render_data() -> str:
		data_calls.append("data")
		return json.dumps({"processes": [], "visits": len(data_calls)})

	try:
		created = create_dashboard_server(("127.0.0.1", 0), render_page, render_data)
	except OSError as e:
		pytest.skip(f"socket creation is unavailable: {e}")
	thread = serve(created)
	try:
		yield created
	finally:
		created.shutdown()
		created.server_close()
		thread.join(timeout=5)


class TestDashboardServer:
	def test_serves_the_page_with_html_content_type(self, server: DashboardServer) -> None:
		status, content_type, body = request(server, "/")

		assert status == 200
		assert content_type == PAGE_CONTENT_TYPE
		assert body == "<html>visits 1</html>"

	def test_serves_process_data_as_json(self, server: DashboardServer) -> None:
		status, content_type, body = request(server, DATA_PATH)

		assert status == 200
		assert content_type == DATA_CONTENT_TYPE
		assert json.loads(body) == {"processes": [], "visits": 1}

	def test_data_path_accepts_trailing_slash_and_query_string(self, server: DashboardServer) -> None:
		assert request(server, f"{DATA_PATH}/")[0] == 200
		assert request(server, f"{DATA_PATH}?fresh=1")[0] == 200

	def test_unknown_path_returns_404(self, server: DashboardServer) -> None:
		status, _, _ = request(server, "/metrics")

		assert status == 404

	def test_both_renderers_run_on_every_request(self) -> None:
		calls: list[str] = []

		def render_page() -> str:
			calls.append("page")
			return "<html></html>"

		def render_data() -> str:
			calls.append("data")
			return "{}"

		try:
			created = create_dashboard_server(("127.0.0.1", 0), render_page, render_data)
		except OSError as e:
			pytest.skip(f"socket creation is unavailable: {e}")
		thread = serve(created)
		try:
			request(created, "/")
			request(created, DATA_PATH)
			request(created, "/")
			request(created, DATA_PATH)
		finally:
			created.shutdown()
			created.server_close()
			thread.join(timeout=5)

		assert calls == ["page", "data", "page", "data"]
