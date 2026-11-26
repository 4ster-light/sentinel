"""Value tests for the dashboard bind helpers and the early checks"""

from io import StringIO

import pytest
import typer
from rich.console import Console
from typer.testing import CliRunner

import sentinel_cli.dashboard as dashboard
from sentinel_cli import app

runner = CliRunner()


def plain_console(monkeypatch: pytest.MonkeyPatch) -> StringIO:
	out = StringIO()
	monkeypatch.setattr(dashboard, "console", Console(file=out, width=80, height=24))
	return out


class TestIsLoopback:
	@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::1", "127.10.0.1"])
	def test_loopback_names(self, host: str) -> None:
		assert dashboard._is_loopback(host) is True

	@pytest.mark.parametrize("host", ["example.com", "10.0.0.1", "0.0.0.0", "", "::2"])
	def test_other_names(self, host: str) -> None:
		assert dashboard._is_loopback(host) is False


class TestCheckBind:
	def test_reports_a_bind_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
		out = plain_console(monkeypatch)

		class FakeSocket:
			def __enter__(self) -> FakeSocket:
				return self

			def __exit__(self, *args: object) -> bool:
				return False

			def bind(self, address: tuple[str, int]) -> None:
				raise OSError("denied")

		monkeypatch.setattr(dashboard.socket, "socket", lambda *args: FakeSocket())

		with pytest.raises(typer.Exit) as excinfo:
			dashboard._check_bind("0.0.0.0", 80)

		assert excinfo.value.exit_code == 1
		assert "Cannot bind 0.0.0.0:80: denied" in out.getvalue()

	def test_accepts_a_free_address(self, monkeypatch: pytest.MonkeyPatch) -> None:
		calls: list[tuple[str, int]] = []

		class FakeSocket:
			def __enter__(self) -> FakeSocket:
				return self

			def __exit__(self, *args: object) -> bool:
				return False

			def bind(self, address: tuple[str, int]) -> None:
				calls.append(address)

		monkeypatch.setattr(dashboard.socket, "socket", lambda *args: FakeSocket())

		dashboard._check_bind("127.0.0.1", 9000)

		assert calls == [("127.0.0.1", 9000)]


class TestDashboardCommand:
	def test_rejects_a_port_below_the_range(self) -> None:
		result = runner.invoke(app, ["dashboard", "--port", "0"])

		assert result.exit_code == 1
		assert "--port must be between 1 and 65535" in result.stdout

	def test_rejects_a_port_above_the_range(self) -> None:
		result = runner.invoke(app, ["dashboard", "--port", "65536"])

		assert result.exit_code == 1
		assert "--port must be between 1 and 65535" in result.stdout

	def test_requires_a_token_beyond_loopback(self) -> None:
		result = runner.invoke(app, ["dashboard", "--host", "0.0.0.0"])

		assert result.exit_code == 1
		assert "--host beyond loopback requires --control-token" in result.stdout
