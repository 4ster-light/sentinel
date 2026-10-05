import os
from pathlib import Path
from sentinel_core.process import restart_process


def test_regression_group_environment_and_relative_paths(
	state, spawn_process, monkeypatch, tmp_path: Path, wait_for
) -> None:
	import json
	import shlex
	import sys

	(tmp_path / "group.env").write_text("SHARED=group-file\nGROUP_FILE=yes\n")
	(tmp_path / "process.env").write_text("SHARED=process-file\n")
	(tmp_path / ".env").write_text("FROM_INITIAL_CWD=yes\n")
	state.create_group("workers", env={"GROUP_ONLY": "yes", "SHARED": "group"}, env_file="group.env")
	result = tmp_path / "environment.json"
	code = f"import json,os,time; open({str(result)!r},'w').write(json.dumps(dict(os.environ))); time.sleep(60)"
	info = spawn_process(
		shlex.join([sys.executable, "-c", code]),
		name="env",
		group="workers",
		env={"SHARED": "process"},
		env_file="process.env",
		cwd=".",
	)
	wait_for(lambda: result.exists() and result.read_text())
	first = json.loads(result.read_text())
	assert first["SHARED"] == "process-file"
	assert first["GROUP_FILE"] == first["GROUP_ONLY"] == first["FROM_INITIAL_CWD"] == "yes"
	assert Path(info.cwd).is_absolute() and Path(info.env_file).is_absolute()
	other = tmp_path / "other"
	other.mkdir()
	(other / ".env").write_text("FROM_INITIAL_CWD=wrong\n")
	monkeypatch.chdir(other)
	monkeypatch.setenv("PYTHONPATH", "/daemon-only")
	first_write = result.stat().st_mtime
	restart_process(state, info.id)
	wait_for(lambda: result.stat().st_mtime > first_write)
	assert json.loads(result.read_text()) == first


def test_regression_user_environment_matches_account(spawn_process, tmp_path: Path, wait_for) -> None:
	import json
	import pwd
	import shlex
	import sys

	account = pwd.getpwuid(os.geteuid())
	result = tmp_path / "user.json"
	code = f"import os,json,time; open({str(result)!r},'w').write(json.dumps([os.getuid(),os.environ['HOME'],os.environ['USER']])); time.sleep(60)"
	spawn_process(shlex.join([sys.executable, "-c", code]), name="user-env", user=account.pw_name)
	wait_for(lambda: result.exists() and result.read_text())
	assert json.loads(result.read_text()) == [account.pw_uid, account.pw_dir, account.pw_name]
