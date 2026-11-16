"""Tests for startup script generation CLI commands"""

import subprocess
from pathlib import Path
from shutil import which

import pytest
from typer.testing import CliRunner

from sentinel_cli import app
from sentinel_cli.startup import render_initd_script, render_systemd_service

runner = CliRunner()


class TestStartupCommands:
	def test_render_systemd_service_minimal(self) -> None:
		unit = render_systemd_service("myservice", ["python", "app.py"])
		assert "[Unit]" in unit
		assert "Description=Sentinel process: myservice" in unit
		assert "ExecStart=/usr/bin/env python app.py" in unit
		assert "Restart=no" in unit
		assert unit.endswith("\n")

	def test_render_systemd_service_with_user_cwd_restart(self) -> None:
		unit = render_systemd_service(
			"myservice",
			["python", "app.py", "--flag", "value with spaces"],
			user="deploy",
			cwd="/srv/app",
			restart=True,
		)
		assert "User=deploy" in unit
		assert "WorkingDirectory=/srv/app" in unit
		assert "Restart=always" in unit
		assert "'value with spaces'" in unit

	def test_startup_systemd_command(self) -> None:
		result = runner.invoke(app, ["startup", "systemd", "--name", "myservice", "python", "app.py"])
		assert result.exit_code == 0
		assert "[Unit]" in result.stdout
		assert "ExecStart=/usr/bin/env python app.py" in result.stdout

	def test_startup_systemd_rejects_empty_name(self) -> None:
		result = runner.invoke(app, ["startup", "systemd", "--name", "   ", "python", "app.py"])
		assert result.exit_code != 0
		assert "service name cannot be empty" in result.stdout.lower()


class TestInitdScript:
	def test_render_initd_script_minimal(self) -> None:
		script = render_initd_script("demo", ["python", "app.py"])

		assert script.startswith("#!/bin/sh\n")
		assert "### BEGIN INIT INFO" in script
		assert "# Provides:          demo" in script
		assert "COMMAND='python app.py'" in script
		assert "RUNAS=''" in script
		assert "WORKDIR=''" in script
		assert "PIDFILE=/run/demo.pid" in script
		assert "LOGFILE=/var/log/demo.log" in script
		assert 'case "${1:-}" in' in script
		assert script.endswith("esac\n")

	def test_render_initd_script_with_user_cwd_and_paths(self) -> None:
		script = render_initd_script(
			"demo",
			["python", "app.py", "--flag", "value with spaces"],
			user="deploy",
			cwd="/srv/app",
			pidfile="/tmp/demo.pid",
			logfile="/tmp/demo.log",
		)

		assert "RUNAS=deploy" in script
		assert "WORKDIR=/srv/app" in script
		assert "PIDFILE=/tmp/demo.pid" in script
		assert "LOGFILE=/tmp/demo.log" in script
		assert "value with spaces" in script

	def test_render_initd_script_is_valid_posix_shell(self, tmp_path: Path) -> None:
		sh = which("sh")
		if sh is None:
			pytest.skip("no POSIX shell available")
		script = render_initd_script("demo", ["python", "app.py"], user="deploy", cwd="/srv/app")
		path = tmp_path / "demo"
		path.write_text(script, encoding="utf-8")

		result = subprocess.run([sh, "-n", str(path)], capture_output=True, text=True, check=False)

		assert result.returncode == 0, result.stderr

	def test_render_initd_script_rejects_empty_name(self) -> None:
		with pytest.raises(ValueError, match="cannot be empty"):
			render_initd_script("  ", ["python", "app.py"])

	def test_render_initd_script_rejects_unsafe_name(self) -> None:
		with pytest.raises(ValueError, match="may only contain"):
			render_initd_script("bad name", ["python", "app.py"])

	def test_render_initd_script_rejects_empty_command(self) -> None:
		with pytest.raises(ValueError, match="Command cannot be empty"):
			render_initd_script("demo", [])

	def test_startup_initd_command(self) -> None:
		result = runner.invoke(app, ["startup", "initd", "--name", "demo", "python", "app.py"])

		assert result.exit_code == 0
		assert "### BEGIN INIT INFO" in result.stdout
		assert "COMMAND='python app.py'" in result.stdout

	def test_startup_initd_command_with_options(self) -> None:
		result = runner.invoke(
			app,
			["startup", "initd", "--name", "demo", "--user", "deploy", "--cwd", "/srv/app", "python", "app.py"],
		)

		assert result.exit_code == 0
		assert "RUNAS=deploy" in result.stdout
		assert "WORKDIR=/srv/app" in result.stdout

	def test_startup_initd_rejects_invalid_name(self) -> None:
		result = runner.invoke(app, ["startup", "initd", "--name", "bad name", "python", "app.py"])

		assert result.exit_code != 0
		assert "may only contain" in result.stdout
