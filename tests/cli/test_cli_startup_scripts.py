"""Tests for startup script generation CLI commands"""

import pytest
from typer.testing import CliRunner

from sentinel_cli import app
from sentinel_cli.startup import render_systemd_service, render_windows_service_script

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


class TestWindowsScript:
	def test_render_windows_script_minimal(self) -> None:
		script = render_windows_service_script("demo", ["python", "app.py"])

		assert script.startswith("#Requires -RunAsAdministrator\n")
		assert "param(" in script
		assert "[switch]$Uninstall" in script
		assert "$ServiceName = 'sentinel-demo'" in script
		assert "$DisplayName = 'Sentinel process: demo'" in script
		assert "$Application = 'python'" in script
		assert "$Arguments = 'app.py'" in script
		assert "$WorkingDirectory = (Get-Location).Path" in script
		assert "& $NssmPath install $ServiceName" in script
		assert "& $NssmPath set $ServiceName Application $Application" in script
		assert "& $NssmPath set $ServiceName AppParameters $Arguments" in script
		assert "& $NssmPath set $ServiceName Start SERVICE_AUTO_START" in script
		assert "if ($Uninstall)" in script
		assert "AppExit" not in script
		assert script.endswith('Write-Host "Installed $ServiceName"\n')

	def test_render_windows_script_quotes_arguments(self) -> None:
		script = render_windows_service_script("demo", ["python", "app.py", "--flag", "value with spaces"])

		assert "$Application = 'python'" in script
		assert "$Arguments = 'app.py --flag \"value with spaces\"'" in script

	def test_render_windows_script_with_user_cwd_and_restart(self) -> None:
		script = render_windows_service_script(
			"demo",
			["python", "app.py"],
			user="CORP\\deploy",
			cwd="C:\\srv\\app",
			restart=True,
		)

		assert "$WorkingDirectory = 'C:\\srv\\app'" in script
		assert "Get-Credential -UserName 'CORP\\deploy'" in script
		assert "ObjectName $Credential.UserName" in script
		assert "& $NssmPath set $ServiceName AppExit Default Restart" in script
		assert "& $NssmPath set $ServiceName AppRestartDelay 5000" in script

	def test_render_windows_script_escapes_single_quotes(self) -> None:
		script = render_windows_service_script("demo", ["python", "app.py"], cwd="C:\\it's here")

		assert "$WorkingDirectory = 'C:\\it''s here'" in script

	def test_render_windows_script_rejects_empty_name(self) -> None:
		with pytest.raises(ValueError, match="cannot be empty"):
			render_windows_service_script("  ", ["python", "app.py"])

	def test_render_windows_script_rejects_unsafe_name(self) -> None:
		with pytest.raises(ValueError, match="may only contain"):
			render_windows_service_script("bad name", ["python", "app.py"])

	def test_render_windows_script_rejects_empty_command(self) -> None:
		with pytest.raises(ValueError, match="Command cannot be empty"):
			render_windows_service_script("demo", [])

	def test_startup_windows_command(self) -> None:
		result = runner.invoke(app, ["startup", "windows", "--name", "demo", "python", "app.py"])

		assert result.exit_code == 0
		assert "#Requires -RunAsAdministrator" in result.stdout
		assert "$ServiceName = 'sentinel-demo'" in result.stdout

	def test_startup_windows_command_with_options(self) -> None:
		result = runner.invoke(
			app,
			["startup", "windows", "--name", "demo", "--cwd", "C:\\srv\\app", "--restart", "python", "app.py"],
		)

		assert result.exit_code == 0
		assert "$WorkingDirectory = 'C:\\srv\\app'" in result.stdout
		assert "AppExit Default Restart" in result.stdout

	def test_startup_windows_rejects_invalid_name(self) -> None:
		result = runner.invoke(app, ["startup", "windows", "--name", "bad name", "python", "app.py"])

		assert result.exit_code != 0
		assert "may only contain" in result.stdout
