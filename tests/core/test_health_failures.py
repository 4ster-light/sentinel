import pytest

from sentinel_core.state import HealthCheckConfig


@pytest.mark.parametrize("target", ["file:///etc/hosts", "ftp://localhost", "not a url", "http://[broken"])
def test_regression_invalid_http_targets_fail(target: str) -> None:
	from sentinel_core.health import _run_http_health_check

	assert not _run_http_health_check(HealthCheckConfig(kind="http", target=target))


def test_regression_http_disconnect_is_a_failed_probe(monkeypatch) -> None:
	from http.client import RemoteDisconnected

	from sentinel_core.health import _run_http_health_check

	def disconnect(*args: object, **kwargs: object) -> None:
		raise RemoteDisconnected("closed without a response")

	monkeypatch.setattr("sentinel_core.health.request.urlopen", disconnect)
	assert not _run_http_health_check(HealthCheckConfig(kind="http", target="http://localhost/health"))


def test_regression_bracketed_ipv6_target() -> None:
	from sentinel_core.health import _parse_host_port

	assert _parse_host_port("[::1]:8080") == ("::1", 8080)
