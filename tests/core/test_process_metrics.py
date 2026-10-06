from pathlib import Path

import psutil

from sentinel_core.process import get_process_status


def test_regression_process_tree_cpu_and_memory(spawn_process, tmp_path: Path, wait_for) -> None:
	import shlex
	import sys

	ready = tmp_path / "busy"
	code = f"data=bytearray(32*1024*1024); open({str(ready)!r},'w').write('ready'); exec('while True: pass')"
	info = spawn_process(shlex.join([sys.executable, "-c", code]) + " & wait", name="busy")
	wait_for(ready.exists)
	status = get_process_status(info)
	assert status.cpu_percent > 0
	assert status.memory_mb > 30


def test_regression_access_denied_status_is_unknown(spawn_process, monkeypatch) -> None:
	info = spawn_process(name="private")

	def denied(*args: object, **kwargs: object) -> None:
		raise psutil.AccessDenied(info.pid)

	with monkeypatch.context() as patch:
		patch.setattr("sentinel_core.process.psutil.Process", denied)
		assert get_process_status(info).status == "unknown"
