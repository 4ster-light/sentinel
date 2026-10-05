from pathlib import Path

from typer.testing import CliRunner

from sentinel_cli import app
from sentinel_core.logs import rotate_log_file, tail_file
from sentinel_core.state import State

runner = CliRunner()


def test_regression_invalid_log_stream_is_rejected(state: State, spawn_process) -> None:
	info = spawn_process(name="logs")
	assert runner.invoke(app, ["logs", str(info.id), "--stream", "invalid"]).exit_code == 1


def test_regression_rotation_keeps_an_open_writer(temp_logs_dir: Path) -> None:
	path = temp_logs_dir / "active.log"
	with path.open("ab", buffering=0) as writer:
		writer.write(b"before\n")
		inode = path.stat().st_ino
		assert rotate_log_file(path, max_bytes=1)
		writer.write(b"after\n")
	assert path.stat().st_ino == inode
	assert path.read_text() == "after\n"
	assert path.with_name("active.log.1").read_text() == "before\n"


def test_regression_tail_zero_and_invalid_utf8(temp_logs_dir: Path) -> None:
	path = temp_logs_dir / "bytes.log"
	path.write_bytes(b"old\ninvalid \xff\nlast\n")
	assert tail_file(path, 0) == []
	assert tail_file(path, 2) == ["invalid \ufffd", "last"]


def test_regression_logs_are_literal_text(temp_logs_dir: Path, capsys) -> None:
	from sentinel_core.logs import show_logs

	path = temp_logs_dir / "markup.log"
	path.write_text("[/tmp/data] loaded\n[bold]literal[/bold]\n")
	show_logs(str(path), str(path), stream="both")
	output = capsys.readouterr().out
	assert "[/tmp/data] loaded" in output
	assert "[bold]literal[/bold]" in output


def test_regression_follow_truncation_replacement_and_partial_lines(temp_logs_dir: Path, monkeypatch, capsys) -> None:
	from sentinel_core.logs import _follow_logs

	path = temp_logs_dir / "follow.log"
	path.write_text("a long initial line\n")
	step = 0

	def write_changes(*args: object) -> None:
		nonlocal step
		step += 1
		if step == 1:
			path.write_text("part")
		elif step == 2:
			with path.open("a") as writer:
				writer.write("ial\n")
		elif step == 3:
			replacement = temp_logs_dir / "replacement"
			replacement.write_text("[/tmp/data] replacement\n")
			replacement.replace(path)
		else:
			raise KeyboardInterrupt

	monkeypatch.setattr("sentinel_core.logs.time.sleep", write_changes)
	_follow_logs(path, temp_logs_dir / "unused", "stdout")
	output = capsys.readouterr().out
	assert "out: partial" in output
	assert "out: [/tmp/data] replacement" in output
	assert "out: part\n" not in output
