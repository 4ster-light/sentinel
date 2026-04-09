"""Health check probes and evaluation helpers"""

from datetime import datetime, timedelta
from socket import create_connection
from urllib import error, request

from .state import HealthCheckConfig, ProcessInfo


def should_run_health_check(process_info: ProcessInfo) -> bool:
	if not process_info.health_check:
		return False
	if process_info.health_last_checked_at is None:
		return True

	try:
		last_checked_at = datetime.fromisoformat(process_info.health_last_checked_at)
	except ValueError:
		return True
	next_check_at = last_checked_at + timedelta(seconds=process_info.health_check.interval_seconds)
	return datetime.now() >= next_check_at


def run_health_check(process_info: ProcessInfo) -> bool:
	if not process_info.health_check:
		return True

	check = process_info.health_check
	if check.kind == "http":
		return _run_http_health_check(check)
	if check.kind == "tcp":
		return _run_tcp_health_check(check)
	return False


def _run_http_health_check(check: HealthCheckConfig) -> bool:
	request_obj = request.Request(check.target, method="GET")
	try:
		with request.urlopen(request_obj, timeout=check.timeout_seconds) as response:
			return 200 <= response.status < 400
	except error.URLError, TimeoutError, ValueError:
		return False


def _run_tcp_health_check(check: HealthCheckConfig) -> bool:
	host, port = _parse_host_port(check.target)
	if not host or port is None:
		return False

	try:
		with create_connection((host, port), timeout=check.timeout_seconds):
			return True
	except OSError:
		return False


def _parse_host_port(target: str) -> tuple[str | None, int | None]:
	parts = target.rsplit(":", 1)
	if len(parts) != 2:
		return None, None

	host = parts[0].strip()
	if not host:
		return None, None

	try:
		port = int(parts[1].strip())
	except ValueError:
		return None, None

	if not (1 <= port <= 65535):
		return None, None

	return host, port
