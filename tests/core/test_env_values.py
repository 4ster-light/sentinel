"""Value tests for the environment loading and merging"""

from pathlib import Path

import pytest

from sentinel_core import env


class TestParseEnvValue:
	@pytest.mark.parametrize(
		("raw", "expected"),
		[
			("  plain  ", "plain"),
			('"quoted"', "quoted"),
			('"a\\"b"', 'a"b'),
			('"line\\nbreak"', "line\nbreak"),
			("'single'", "single"),
			('"unterminated', '"unterminated'),
		],
	)
	def test_parses_values(self, raw: str, expected: str) -> None:
		assert env._parse_env_value(raw) == expected


class TestParseEnvLine:
	def test_skips_empty_lines_and_comments(self) -> None:
		assert env._parse_env_line("") is None
		assert env._parse_env_line("   ") is None
		assert env._parse_env_line("  # comment") is None

	def test_parses_a_pair_with_spaces(self) -> None:
		assert env._parse_env_line("  KEY = value  ") == ("KEY", "value")

	def test_parses_an_empty_value(self) -> None:
		assert env._parse_env_line("KEY=") == ("KEY", "")

	def test_rejects_a_leading_digit(self) -> None:
		assert env._parse_env_line("1KEY=value") is None

	def test_rejects_a_line_without_equals(self) -> None:
		assert env._parse_env_line("KEY value") is None


class TestLoadEnvFile:
	def test_reads_pairs_and_skips_comments(self, tmp_path: Path) -> None:
		path = tmp_path / ".env"
		path.write_text('# comment\nA=1\n\nB="two words"\n')

		assert env.load_env_file(path) == {"A": "1", "B": "two words"}

	def test_reports_a_missing_file(self, tmp_path: Path) -> None:
		path = tmp_path / "absent.env"

		with pytest.raises(FileNotFoundError) as excinfo:
			env.load_env_file(path)

		assert str(excinfo.value) == f"Environment file not found: {path}"

	def test_reports_a_directory(self, tmp_path: Path) -> None:
		with pytest.raises(ValueError, match="Environment path is not a file") as excinfo:
			env.load_env_file(tmp_path)

		assert str(excinfo.value) == f"Environment path is not a file: {tmp_path}"


class TestFindGlobalEnvFiles:
	def test_finds_home_and_cwd_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		home = tmp_path / "home"
		(home / ".sentinel").mkdir(parents=True)
		(home / ".sentinel" / ".env").write_text("A=1\n")
		monkeypatch.setenv("HOME", str(home))
		monkeypatch.chdir(tmp_path)
		(tmp_path / ".env").write_text("B=2\n")

		assert env.find_global_env_files() == [home / ".sentinel" / ".env", tmp_path / ".env"]

	def test_returns_empty_without_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setenv("HOME", str(tmp_path / "home"))
		monkeypatch.chdir(tmp_path)

		assert env.find_global_env_files() == []


class TestMergeEnvironments:
	def test_later_dicts_win_and_none_is_skipped(self) -> None:
		assert env.merge_environments({"A": "1", "B": "1"}, None, {"A": "2"}) == {"A": "2", "B": "1"}


class TestBuildProcessEnvironment:
	def test_applies_the_documented_order(self, tmp_path: Path) -> None:
		group_file = tmp_path / "group.env"
		group_file.write_text("A=group-file\nB=group-file\n")
		process_file = tmp_path / "process.env"
		process_file.write_text("A=process-file\nC=process-file\n")

		result = env.build_process_environment(
			system_env=False,
			global_env_files=False,
			group_env={"A": "group", "B": "group"},
			group_env_file=group_file,
			process_env={"A": "process", "C": "process"},
			process_env_file=process_file,
			override_env={"A": "override"},
		)

		assert result == {"A": "override", "B": "group-file", "C": "process-file"}

	def test_loads_the_global_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		home = tmp_path / "home"
		(home / ".sentinel").mkdir(parents=True)
		(home / ".sentinel" / ".env").write_text("A=home\nB=home\n")
		monkeypatch.setenv("HOME", str(home))
		monkeypatch.chdir(tmp_path)
		(tmp_path / ".env").write_text("B=cwd\n")

		result = env.build_process_environment(system_env=False)

		assert result == {"A": "home", "B": "cwd"}

	def test_keeps_the_system_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
		monkeypatch.setenv("SENTINEL_TEST_MARKER", "1")

		result = env.build_process_environment(global_env_files=False)

		assert result["SENTINEL_TEST_MARKER"] == "1"

	def test_reports_a_group_file_error(self, tmp_path: Path) -> None:
		path = tmp_path / "absent.env"

		with pytest.raises(ValueError, match="Cannot load group env file"):
			env.build_process_environment(system_env=False, global_env_files=False, group_env_file=path)

	def test_reports_a_process_file_error(self, tmp_path: Path) -> None:
		path = tmp_path / "absent.env"

		with pytest.raises(ValueError, match="Cannot load process env file"):
			env.build_process_environment(system_env=False, global_env_files=False, process_env_file=path)

	def test_ignores_an_unreadable_global_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
		home = tmp_path / "home"
		(home / ".sentinel").mkdir(parents=True)
		(home / ".sentinel" / ".env").write_text("not a pair\n")
		monkeypatch.setenv("HOME", str(home))
		monkeypatch.chdir(tmp_path)

		assert env.build_process_environment(system_env=False) == {}
