"""Value tests for the log rotation, tail and display helpers"""

from collections.abc import Callable, Iterable
from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console

import sentinel_core.logs as logs


class TestRotateLogFile:
	def test_rejects_a_non_positive_max(self, tmp_path: Path) -> None:
		with pytest.raises(ValueError, match="max_bytes must be greater than 0"):
			logs.rotate_log_file(tmp_path / "x.log", max_bytes=0)

	def test_rejects_a_low_backup_count(self, tmp_path: Path) -> None:
		with pytest.raises(ValueError, match="backups must be at least 1"):
			logs.rotate_log_file(tmp_path / "x.log", backups=0)

	def test_keeps_a_file_below_the_limit(self, tmp_path: Path) -> None:
		path = tmp_path / "x.log"
		path.write_text("abc")

		assert logs.rotate_log_file(path, max_bytes=4) is False
		assert path.read_text() == "abc"
		assert not (tmp_path / "x.log.1").exists()

	def test_rotates_at_the_exact_limit(self, tmp_path: Path) -> None:
		path = tmp_path / "x.log"
		path.write_text("abcd")

		assert logs.rotate_log_file(path, max_bytes=4, backups=2) is True
		assert path.read_text() == ""
		assert (tmp_path / "x.log.1").read_text() == "abcd"

	def test_shifts_the_backups(self, tmp_path: Path) -> None:
		path = tmp_path / "x.log"
		path.write_text("newest")
		(tmp_path / "x.log.1").write_text("old-1")
		(tmp_path / "x.log.2").write_text("old-2")

		logs.rotate_log_file(path, max_bytes=1, backups=2)

		assert (tmp_path / "x.log.1").read_text() == "newest"
		assert (tmp_path / "x.log.2").read_text() == "old-1"
		assert not (tmp_path / "x.log.3").exists()

	def test_keeps_the_inode(self, tmp_path: Path) -> None:
		path = tmp_path / "x.log"
		path.write_text("abcd")
		inode = path.stat().st_ino

		logs.rotate_log_file(path, max_bytes=1)

		assert path.stat().st_ino == inode

	def test_a_missing_file_is_not_rotated(self, tmp_path: Path) -> None:
		assert logs.rotate_log_file(tmp_path / "absent.log", max_bytes=1) is False


class TestTailFile:
	def test_reads_the_last_lines(self, tmp_path: Path) -> None:
		path = tmp_path / "x.log"
		path.write_text("one\ntwo\nthree\n")

		assert logs.tail_file(path, lines=2) == ["two", "three"]

	def test_strips_windows_line_endings(self, tmp_path: Path) -> None:
		path = tmp_path / "x.log"
		path.write_bytes(b"a\r\nb\r\n")

		assert logs.tail_file(path, lines=5) == ["a", "b"]

	def test_zero_lines_returns_empty(self, tmp_path: Path) -> None:
		path = tmp_path / "x.log"
		path.write_text("a\n")

		assert logs.tail_file(path, lines=0) == []

	def test_a_missing_file_returns_empty(self, tmp_path: Path) -> None:
		assert logs.tail_file(tmp_path / "absent.log") == []

	def test_replaces_invalid_bytes(self, tmp_path: Path) -> None:
		path = tmp_path / "x.log"
		path.write_bytes(b"ok\n\xff\n")

		assert logs.tail_file(path, lines=5) == ["ok", "\ufffd"]


class TestRotateProcessLogs:
	def test_rotates_both_streams(self, tmp_path: Path) -> None:
		stdout = tmp_path / "out.log"
		stderr = tmp_path / "err.log"
		stdout.write_text("out")
		stderr.write_text("err")

		assert logs.rotate_process_logs(str(stdout), str(stderr), max_bytes=1, backups=2) == (True, True)
		assert (tmp_path / "out.log.1").read_text() == "out"
		assert (tmp_path / "err.log.1").read_text() == "err"

	def test_reports_no_rotation(self, tmp_path: Path) -> None:
		stdout = tmp_path / "out.log"
		stderr = tmp_path / "err.log"
		stdout.write_text("out")

		assert logs.rotate_process_logs(str(stdout), str(stderr), max_bytes=10, backups=2) == (False, False)


class TestClearLogs:
	def test_truncates_an_existing_file(self, tmp_path: Path) -> None:
		path = tmp_path / "x.log"
		path.write_text("content")

		logs.clear_logs(str(path), str(tmp_path / "absent.log"))

		assert path.read_text() == ""
		assert not (tmp_path / "absent.log").exists()


class TestShowLogs:
	def test_rejects_an_unknown_stream(self, tmp_path: Path) -> None:
		with pytest.raises(ValueError, match="stream must be stdout, stderr, or both"):
			logs.show_logs(str(tmp_path / "out.log"), str(tmp_path / "err.log"), stream="other")

	def test_rejects_negative_lines(self, tmp_path: Path) -> None:
		with pytest.raises(ValueError, match="lines must be non-negative"):
			logs.show_logs(str(tmp_path / "out.log"), str(tmp_path / "err.log"), lines=-1)

	def test_renders_both_blocks(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		out = StringIO()
		monkeypatch.setattr(logs, "console", Console(file=out, width=200, height=24))
		stdout = tmp_path / "out.log"
		stderr = tmp_path / "err.log"
		stdout.write_text("line-1\nline-2\n")
		stderr.write_text("err-1\n")

		logs.show_logs(str(stdout), str(stderr), lines=10, stream="both")

		assert out.getvalue() == (f"═══ stdout ({stdout}) ═══\nline-1\nline-2\n\n═══ stderr ({stderr}) ═══\nerr-1\n")

	def test_renders_one_stream(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		out = StringIO()
		monkeypatch.setattr(logs, "console", Console(file=out, width=200, height=24))
		stdout = tmp_path / "out.log"
		stderr = tmp_path / "err.log"
		stdout.write_text("line-1\n")
		stderr.write_text("err-1\n")

		logs.show_logs(str(stdout), str(stderr), lines=10, stream="stderr")

		assert out.getvalue() == f"\n═══ stderr ({stderr}) ═══\nerr-1\n"


def append_to(path: Path, text: str) -> None:
	with path.open("a", encoding="utf-8") as stream:
		stream.write(text)


def follow(
	monkeypatch: pytest.MonkeyPatch,
	stdout: Path,
	stderr: Path,
	actions: Iterable[Callable[[], None]] | None = None,
	stream: str = "both",
) -> str:
	pending = list(actions or [])

	def sleep(seconds: float) -> None:
		if not pending:
			raise KeyboardInterrupt
		pending.pop(0)()

	monkeypatch.setattr("time.sleep", sleep)
	out = StringIO()
	monkeypatch.setattr(logs, "console", Console(file=out, width=200000, height=24))
	logs._follow_logs(stdout, stderr, stream)
	return out.getvalue()


class TestShowLogsExact:
	def test_prints_both_stream_blocks(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		stdout = tmp_path / "out.log"
		stderr = tmp_path / "err.log"
		stdout.write_text("a\nb\n")
		stderr.write_text("e\n")
		out = StringIO()
		monkeypatch.setattr(logs, "console", Console(file=out, width=200, height=24))

		logs.show_logs(str(stdout), str(stderr), lines=10, stream="both")

		assert out.getvalue() == f"═══ stdout ({stdout}) ═══\na\nb\n\n═══ stderr ({stderr}) ═══\ne\n"

	def test_prints_only_the_stdout_block(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		stdout = tmp_path / "out.log"
		stderr = tmp_path / "err.log"
		stdout.write_text("a\n")
		stderr.write_text("e\n")
		out = StringIO()
		monkeypatch.setattr(logs, "console", Console(file=out, width=200, height=24))

		logs.show_logs(str(stdout), str(stderr), lines=10, stream="stdout")

		assert out.getvalue() == f"═══ stdout ({stdout}) ═══\na\n"

	def test_prints_only_the_stderr_block(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		stdout = tmp_path / "out.log"
		stderr = tmp_path / "err.log"
		stdout.write_text("a\n")
		stderr.write_text("e\n")
		out = StringIO()
		monkeypatch.setattr(logs, "console", Console(file=out, width=200, height=24))

		logs.show_logs(str(stdout), str(stderr), lines=10, stream="stderr")

		assert out.getvalue() == f"\n═══ stderr ({stderr}) ═══\ne\n"

	def test_prints_the_follow_notice(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		stdout = tmp_path / "out.log"
		stdout.write_text("a\n")
		calls: list[tuple[Path, Path, str]] = []
		monkeypatch.setattr(logs, "_follow_logs", lambda path, err, stream: calls.append((path, err, stream)))
		out = StringIO()
		monkeypatch.setattr(logs, "console", Console(file=out, width=200, height=24))

		logs.show_logs(str(stdout), str(tmp_path / "err.log"), follow=True, stream="stdout")

		assert out.getvalue() == f"═══ stdout ({stdout}) ═══\na\n\nFollowing logs (Ctrl+C to stop)...\n"
		assert calls == [(stdout, tmp_path / "err.log", "stdout")]


class TestFollowLogs:
	def test_starts_at_the_end_of_an_existing_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		stdout = tmp_path / "out.log"
		stdout.write_text("old\n")

		text = follow(monkeypatch, stdout, tmp_path / "err.log")

		assert text == "\nStopped following logs.\n"

	def test_prints_appended_lines_and_the_stop_message(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		stdout = tmp_path / "out.log"
		stdout.write_text("")

		text = follow(monkeypatch, stdout, tmp_path / "err.log", [lambda: append_to(stdout, "hello\nworld\n")])

		assert text == "out: hello\nout: world\n\nStopped following logs.\n"

	def test_waits_for_a_newline_before_printing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		stdout = tmp_path / "out.log"
		stdout.write_text("")
		actions = [lambda: append_to(stdout, "abc"), lambda: append_to(stdout, "def\n")]

		text = follow(monkeypatch, stdout, tmp_path / "err.log", actions)

		assert text == "out: abcdef\n\nStopped following logs.\n"

	def test_reopens_a_replaced_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		stdout = tmp_path / "out.log"
		stdout.write_text("old\n")
		replacement = tmp_path / "new.log"
		replacement.write_text("new\n")

		def swap() -> None:
			replacement.replace(stdout)

		text = follow(monkeypatch, stdout, tmp_path / "err.log", [swap])

		assert text == "out: new\n\nStopped following logs.\n"

	def test_prints_only_the_requested_stream(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		stdout = tmp_path / "out.log"
		stderr = tmp_path / "err.log"
		stdout.write_text("")
		stderr.write_text("")
		actions = [lambda: append_to(stdout, "o\n"), lambda: append_to(stderr, "e\n")]

		text = follow(monkeypatch, stdout, stderr, actions, stream="stderr")

		assert text == "err: e\n\nStopped following logs.\n"

	def test_flushes_output_without_newlines(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		stdout = tmp_path / "out.log"
		stdout.write_text("")

		text = follow(monkeypatch, stdout, tmp_path / "err.log", [lambda: append_to(stdout, "x" * 70000)])

		assert text == "out: " + "x" * 70000 + "\n\nStopped following logs.\n"
