"""Whole-script tests for the service templates"""

from pathlib import Path

import pytest

from sentinel_cli.startup import render_initd_script, render_systemd_service, render_windows_service_script

GOLDEN = Path(__file__).parent / "golden"
NAME = "demo"
COMMAND = ["/usr/bin/python", "/srv/app/app.py"]
USER = "svc"
CWD = "/srv/app"
PIDFILE = "/run/demo.pid"
LOGFILE = "/var/log/demo.log"
KINDS = ("systemd", "initd", "windows")


def render(kind: str) -> str:
	if kind == "systemd":
		return render_systemd_service(NAME, COMMAND, user=USER, cwd=CWD, restart=True)
	if kind == "initd":
		return render_initd_script(NAME, COMMAND, user=USER, cwd=CWD, pidfile=PIDFILE, logfile=LOGFILE)
	return render_windows_service_script(NAME, COMMAND, user=USER, cwd=CWD, restart=True)


@pytest.mark.parametrize("kind", KINDS)
def test_the_whole_script_matches_the_golden_file(kind: str) -> None:
	assert render(kind) == (GOLDEN / f"{kind}.txt").read_text()
