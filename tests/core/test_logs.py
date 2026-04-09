from sentinel_core.logs import clear_logs, rotate_log_file, rotate_process_logs, tail_file

from pathlib import Path


class TestTailFile:
	def test_tail_file_full_content(self, temp_logs_dir: Path):
		log_file = temp_logs_dir / "test.log"
		log_file.write_text("line 1\nline 2\nline 3\n")

		lines = tail_file(log_file, lines=50)

		assert len(lines) == 3
		assert lines == ["line 1", "line 2", "line 3"]

	def test_tail_file_limited(self, temp_logs_dir: Path):
		log_file = temp_logs_dir / "test.log"
		content = "\n".join([f"line {i}" for i in range(1, 101)])
		log_file.write_text(content)

		lines = tail_file(log_file, lines=10)

		assert len(lines) == 10
		assert lines[0] == "line 91"
		assert lines[-1] == "line 100"

	def test_tail_file_nonexistent(self, temp_logs_dir: Path):
		log_file = temp_logs_dir / "nonexistent.log"

		lines = tail_file(log_file, lines=50)

		assert lines == []

	def test_tail_file_empty(self, temp_logs_dir: Path):
		log_file = temp_logs_dir / "empty.log"
		log_file.write_text("")

		lines = tail_file(log_file, lines=50)

		assert lines == []

	def test_tail_file_no_trailing_newline(self, temp_logs_dir: Path):
		log_file = temp_logs_dir / "test.log"
		log_file.write_text("line 1\nline 2\nline 3")

		lines = tail_file(log_file, lines=50)

		assert len(lines) == 3
		assert lines == ["line 1", "line 2", "line 3"]


class TestClearLogs:
	def test_clear_logs(self, temp_logs_dir: Path):
		stdout_log = temp_logs_dir / "test.stdout.log"
		stderr_log = temp_logs_dir / "test.stderr.log"

		stdout_log.write_text("stdout content\n")
		stderr_log.write_text("stderr content\n")

		assert stdout_log.exists()
		assert stderr_log.exists()
		assert len(stdout_log.read_text()) > 0
		assert len(stderr_log.read_text()) > 0

		clear_logs(str(stdout_log), str(stderr_log))

		assert stdout_log.exists()
		assert stderr_log.exists()
		assert stdout_log.read_text() == ""
		assert stderr_log.read_text() == ""

	def test_clear_logs_nonexistent(self, temp_logs_dir: Path):
		stdout_log = temp_logs_dir / "nonexistent.stdout.log"
		stderr_log = temp_logs_dir / "nonexistent.stderr.log"

		# Should not raise an error
		clear_logs(str(stdout_log), str(stderr_log))

		# Files should still not exist
		assert not stdout_log.exists()
		assert not stderr_log.exists()

	def test_clear_logs_one_exists(self, temp_logs_dir: Path):
		stdout_log = temp_logs_dir / "test.stdout.log"
		stderr_log = temp_logs_dir / "test.stderr.log"

		stdout_log.write_text("stdout content\n")

		clear_logs(str(stdout_log), str(stderr_log))

		assert stdout_log.exists()
		assert stdout_log.read_text() == ""
		assert not stderr_log.exists()


class TestShowLogs:
	def test_show_logs_both_streams(self, temp_logs_dir: Path, capsys):
		from sentinel_core.logs import show_logs

		stdout_log = temp_logs_dir / "test.stdout.log"
		stderr_log = temp_logs_dir / "test.stderr.log"

		stdout_log.write_text("stdout line 1\nstdout line 2\n")
		stderr_log.write_text("stderr line 1\nstderr line 2\n")

		show_logs(str(stdout_log), str(stderr_log), lines=50, follow=False, stream="both")

		captured = capsys.readouterr()
		output = captured.out

		# Check that both streams are shown
		assert "stdout line 1" in output
		assert "stdout line 2" in output

		assert "stderr line 1" in output
		assert "stderr line 2" in output

	def test_show_logs_stdout_only(self, temp_logs_dir: Path, capsys):
		from sentinel_core.logs import show_logs

		stdout_log = temp_logs_dir / "test.stdout.log"
		stderr_log = temp_logs_dir / "test.stderr.log"

		stdout_log.write_text("stdout line 1\n")
		stderr_log.write_text("stderr line 1\n")

		show_logs(str(stdout_log), str(stderr_log), lines=50, follow=False, stream="stdout")

		captured = capsys.readouterr()
		output = captured.out

		assert "stdout line 1" in output
		assert "stderr line 1" not in output

	def test_show_logs_stderr_only(self, temp_logs_dir, capsys):
		from sentinel_core.logs import show_logs

		stdout_log = temp_logs_dir / "test.stdout.log"
		stderr_log = temp_logs_dir / "test.stderr.log"

		stdout_log.write_text("stdout line 1\n")
		stderr_log.write_text("stderr line 1\n")

		show_logs(str(stdout_log), str(stderr_log), lines=50, follow=False, stream="stderr")

		captured = capsys.readouterr()
		output = captured.out

		assert "stdout line 1" not in output
		assert "stderr line 1" in output

	def test_show_logs_nonexistent(self, temp_logs_dir, capsys):
		from sentinel_core.logs import show_logs

		stdout_log = temp_logs_dir / "nonexistent.stdout.log"
		stderr_log = temp_logs_dir / "nonexistent.stderr.log"

		# Should not raise an error
		show_logs(str(stdout_log), str(stderr_log), lines=50, follow=False, stream="both")


class TestLogRotation:
	def test_rotate_log_file_when_above_max_size(self, temp_logs_dir: Path) -> None:
		log_file = temp_logs_dir / "rotate.log"
		log_file.write_text("abcdef")

		rotated = rotate_log_file(log_file, max_bytes=4, backups=2)

		assert rotated is True
		assert log_file.exists()
		assert log_file.read_text() == ""
		assert (temp_logs_dir / "rotate.log.1").read_text() == "abcdef"

	def test_rotate_log_file_when_below_max_size(self, temp_logs_dir: Path) -> None:
		log_file = temp_logs_dir / "rotate.log"
		log_file.write_text("abc")

		rotated = rotate_log_file(log_file, max_bytes=4, backups=2)

		assert rotated is False
		assert log_file.read_text() == "abc"
		assert not (temp_logs_dir / "rotate.log.1").exists()

	def test_rotate_log_file_shifts_existing_backups(self, temp_logs_dir: Path) -> None:
		log_file = temp_logs_dir / "rotate.log"
		log_file.write_text("newest")
		(temp_logs_dir / "rotate.log.1").write_text("old-1")
		(temp_logs_dir / "rotate.log.2").write_text("old-2")

		rotate_log_file(log_file, max_bytes=1, backups=2)

		assert (temp_logs_dir / "rotate.log.1").read_text() == "newest"
		assert (temp_logs_dir / "rotate.log.2").read_text() == "old-1"

	def test_rotate_process_logs_for_both_streams(self, temp_logs_dir: Path) -> None:
		stdout_log = temp_logs_dir / "test.stdout.log"
		stderr_log = temp_logs_dir / "test.stderr.log"
		stdout_log.write_text("stdout data")
		stderr_log.write_text("stderr data")

		stdout_rotated, stderr_rotated = rotate_process_logs(
			str(stdout_log),
			str(stderr_log),
			max_bytes=1,
			backups=2,
		)

		assert stdout_rotated is True
		assert stderr_rotated is True
		assert (temp_logs_dir / "test.stdout.log.1").read_text() == "stdout data"
		assert (temp_logs_dir / "test.stderr.log.1").read_text() == "stderr data"
