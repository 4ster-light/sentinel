import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from sentinel.health import run_health_check, should_run_health_check
from sentinel.state import HealthCheckConfig, ProcessInfo


class _HealthyHandler(BaseHTTPRequestHandler):
	def do_GET(self) -> None:
		self.send_response(200)
		self.end_headers()
		self.wfile.write(b"ok")

	def log_message(self, format: str, *args: object) -> None:
		return


def _build_process_info(health_check: HealthCheckConfig | None = None, last_checked: str | None = None) -> ProcessInfo:
	return ProcessInfo(
		id=1,
		pid=1,
		name="health-test",
		cmd="echo test",
		cwd="/tmp",
		restart=False,
		started_at="2024-01-01T00:00:00",
		stdout_log="/tmp/health.stdout.log",
		stderr_log="/tmp/health.stderr.log",
		health_check=health_check,
		health_last_checked_at=last_checked,
	)


class TestShouldRunHealthCheck:
	def test_returns_false_without_health_check(self) -> None:
		process_info = _build_process_info(health_check=None)
		assert should_run_health_check(process_info) is False

	def test_returns_true_when_never_checked(self) -> None:
		health_check = HealthCheckConfig(kind="tcp", target="127.0.0.1:80")
		process_info = _build_process_info(health_check=health_check)
		assert should_run_health_check(process_info) is True

	def test_returns_true_for_invalid_last_checked_timestamp(self) -> None:
		health_check = HealthCheckConfig(kind="tcp", target="127.0.0.1:80")
		process_info = _build_process_info(health_check=health_check, last_checked="invalid")
		assert should_run_health_check(process_info) is True


class TestRunHealthCheck:
	def test_http_health_check_success(self) -> None:
		http_server = HTTPServer(("127.0.0.1", 0), _HealthyHandler)
		thread = threading.Thread(target=http_server.serve_forever, daemon=True)
		thread.start()

		try:
			host = http_server.server_name
			port = http_server.server_port
			health_check = HealthCheckConfig(kind="http", target=f"http://{host}:{port}", timeout_seconds=1.0)
			process_info = _build_process_info(health_check=health_check)

			assert run_health_check(process_info) is True
		finally:
			http_server.shutdown()
			http_server.server_close()

	def test_http_health_check_failure(self) -> None:
		health_check = HealthCheckConfig(kind="http", target="http://127.0.0.1:1", timeout_seconds=0.1)
		process_info = _build_process_info(health_check=health_check)
		assert run_health_check(process_info) is False

	def test_tcp_health_check_success(self) -> None:
		server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		server_socket.bind(("127.0.0.1", 0))
		server_socket.listen(1)
		host, port = server_socket.getsockname()

		try:
			health_check = HealthCheckConfig(kind="tcp", target=f"{host}:{port}", timeout_seconds=1.0)
			process_info = _build_process_info(health_check=health_check)
			assert run_health_check(process_info) is True
		finally:
			server_socket.close()

	def test_tcp_health_check_failure(self) -> None:
		health_check = HealthCheckConfig(kind="tcp", target="127.0.0.1:1", timeout_seconds=0.1)
		process_info = _build_process_info(health_check=health_check)
		assert run_health_check(process_info) is False

	def test_tcp_health_check_invalid_target(self) -> None:
		health_check = HealthCheckConfig(kind="tcp", target="invalid-target")
		process_info = _build_process_info(health_check=health_check)
		assert run_health_check(process_info) is False

	def test_unknown_health_check_kind(self) -> None:
		health_check = HealthCheckConfig(kind="unknown", target="example")
		process_info = _build_process_info(health_check=health_check)
		assert run_health_check(process_info) is False
