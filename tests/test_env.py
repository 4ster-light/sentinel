"""Tests for environment variable loading and management"""

from pathlib import Path

import pytest

from sentinel.env import (
	build_process_environment,
	find_global_env_files,
	load_env_file,
	merge_environments,
)


class TestLoadEnvFile:
	"""Tests for load_env_file function"""

	def test_load_valid_env_file(self, tmp_path: Path):
		"""Test loading a valid .env file"""
		env_file = tmp_path / ".env"
		env_file.write_text("VAR1=value1\nVAR2=value2\n")

		result = load_env_file(env_file)
		assert result == {"VAR1": "value1", "VAR2": "value2"}

	def test_load_env_file_with_quotes(self, tmp_path: Path):
		"""Test loading .env file with quoted values"""
		env_file = tmp_path / ".env"
		env_file.write_text("VAR1=\"quoted value\"\nVAR2='single quoted'\n")

		result = load_env_file(env_file)
		assert result["VAR1"] == "quoted value"
		assert result["VAR2"] == "single quoted"

	def test_load_env_file_with_comments(self, tmp_path: Path):
		"""Test loading .env file with comments"""
		env_file = tmp_path / ".env"
		env_file.write_text("# Comment\nVAR1=value1\n# Another comment\nVAR2=value2\n")

		result = load_env_file(env_file)
		assert result == {"VAR1": "value1", "VAR2": "value2"}

	def test_load_env_file_with_empty_lines(self, tmp_path: Path):
		"""Test loading .env file with empty lines"""
		env_file = tmp_path / ".env"
		env_file.write_text("VAR1=value1\n\nVAR2=value2\n\n")

		result = load_env_file(env_file)
		assert result == {"VAR1": "value1", "VAR2": "value2"}

	def test_load_env_file_not_found(self):
		"""Test loading non-existent file raises FileNotFoundError"""
		with pytest.raises(FileNotFoundError):
			load_env_file("/nonexistent/path/.env")

	def test_load_env_file_is_directory(self, tmp_path: Path):
		"""Test loading directory raises ValueError"""
		with pytest.raises(ValueError):
			load_env_file(tmp_path)

	def test_load_env_file_with_equals_in_value(self, tmp_path: Path):
		"""Test loading .env with equals sign in value"""
		env_file = tmp_path / ".env"
		env_file.write_text("DATABASE_URL=postgres://user:pass@localhost/db\n")

		result = load_env_file(env_file)
		assert result["DATABASE_URL"] == "postgres://user:pass@localhost/db"

	def test_load_env_file_with_multiline_values(self, tmp_path: Path):
		"""Test loading .env with multiline values (if supported)"""
		env_file = tmp_path / ".env"
		env_file.write_text('VAR1="line1\nline2"\n')

		result = load_env_file(env_file)
		assert "VAR1" in result

	def test_load_env_file_preserves_whitespace_in_quoted_values(self, tmp_path: Path):
		"""Test that whitespace in quoted values is preserved"""
		env_file = tmp_path / ".env"
		env_file.write_text('VAR1="  value with spaces  "\n')

		result = load_env_file(env_file)
		assert result["VAR1"] == "  value with spaces  "


class TestMergeEnvironments:
	"""Tests for merge_environments function"""

	def test_merge_single_dict(self):
		"""Test merging single dictionary"""
		env1 = {"VAR1": "value1"}
		result = merge_environments(env1)
		assert result == {"VAR1": "value1"}

	def test_merge_multiple_dicts(self):
		"""Test merging multiple dictionaries"""
		env1 = {"VAR1": "value1"}
		env2 = {"VAR2": "value2"}
		env3 = {"VAR3": "value3"}

		result = merge_environments(env1, env2, env3)
		assert result == {"VAR1": "value1", "VAR2": "value2", "VAR3": "value3"}

	def test_merge_with_overrides(self):
		"""Test that later dicts override earlier ones"""
		env1 = {"VAR1": "value1", "SHARED": "env1"}
		env2 = {"VAR2": "value2", "SHARED": "env2"}

		result = merge_environments(env1, env2)
		assert result["SHARED"] == "env2"
		assert result["VAR1"] == "value1"

	def test_merge_with_none(self):
		"""Test merging with None values"""
		env1 = {"VAR1": "value1"}
		result = merge_environments(env1, None, {"VAR2": "value2"})

		assert result == {"VAR1": "value1", "VAR2": "value2"}

	def test_merge_empty_dicts(self):
		"""Test merging empty dictionaries"""
		result = merge_environments({}, {}, {})
		assert result == {}

	def test_merge_no_args(self):
		"""Test merging with no arguments"""
		result = merge_environments()
		assert result == {}

	def test_merge_all_none(self):
		"""Test merging all None values"""
		result = merge_environments(None, None, None)
		assert result == {}


class TestFindGlobalEnvFiles:
	"""Tests for find_global_env_files function"""

	def test_find_no_env_files(self, monkeypatch, tmp_path: Path):
		"""Test when no .env files exist"""
		monkeypatch.setenv("HOME", str(tmp_path))
		monkeypatch.chdir(tmp_path)

		result = find_global_env_files()
		assert result == []

	def test_find_sentinel_env_file(self, monkeypatch, tmp_path: Path):
		"""Test finding ~/.sentinel/.env"""
		home = tmp_path / "home"
		home.mkdir()
		sentinel_dir = home / ".sentinel"
		sentinel_dir.mkdir()
		env_file = sentinel_dir / ".env"
		env_file.write_text("VAR=value")

		monkeypatch.setenv("HOME", str(home))
		monkeypatch.chdir(tmp_path)

		result = find_global_env_files()
		assert len(result) == 1
		assert result[0] == env_file

	def test_find_cwd_env_file(self, monkeypatch, tmp_path: Path):
		"""Test finding ./.env in current directory"""
		env_file = tmp_path / ".env"
		env_file.write_text("VAR=value")

		monkeypatch.chdir(tmp_path)

		result = find_global_env_files()
		assert env_file in result

	def test_find_both_env_files(self, monkeypatch, tmp_path: Path):
		"""Test finding both ~/.sentinel/.env and ./.env"""
		home = tmp_path / "home"
		home.mkdir()
		sentinel_dir = home / ".sentinel"
		sentinel_dir.mkdir()
		sentinel_env = sentinel_dir / ".env"
		sentinel_env.write_text("VAR1=value1")

		cwd_env = tmp_path / ".env"
		cwd_env.write_text("VAR2=value2")

		monkeypatch.setenv("HOME", str(home))
		monkeypatch.chdir(tmp_path)

		result = find_global_env_files()
		assert len(result) == 2
		assert sentinel_env in result
		assert cwd_env in result


class TestBuildProcessEnvironment:
	"""Tests for build_process_environment function"""

	def test_build_with_system_env_only(self):
		"""Test building environment with only system env"""
		result = build_process_environment(system_env=True, global_env_files=False)

		# Should contain system environment
		assert "PATH" in result or "HOME" in result or len(result) > 0

	def test_build_with_process_env(self):
		"""Test building environment with process env"""
		process_env = {"CUSTOM_VAR": "custom_value"}
		result = build_process_environment(
			system_env=False,
			global_env_files=False,
			process_env=process_env,
		)

		assert result["CUSTOM_VAR"] == "custom_value"

	def test_build_with_override_env(self):
		"""Test that override env has highest priority"""
		process_env = {"VAR": "process"}
		override_env = {"VAR": "override"}

		result = build_process_environment(
			system_env=False,
			global_env_files=False,
			process_env=process_env,
			override_env=override_env,
		)

		assert result["VAR"] == "override"

	def test_build_with_process_env_file(self, tmp_path: Path):
		"""Test building environment with process env file"""
		env_file = tmp_path / "process.env"
		env_file.write_text("FILE_VAR=file_value")

		result = build_process_environment(
			system_env=False,
			global_env_files=False,
			process_env_file=env_file,
		)

		assert result["FILE_VAR"] == "file_value"

	def test_build_with_group_env(self):
		"""Test building environment with group env"""
		group_env = {"GROUP_VAR": "group_value"}
		result = build_process_environment(
			system_env=False,
			global_env_files=False,
			group_env=group_env,
		)

		assert result["GROUP_VAR"] == "group_value"

	def test_build_env_merge_precedence(self, tmp_path: Path):
		"""Test complete merge precedence order"""
		# Create env files
		group_env_file = tmp_path / "group.env"
		group_env_file.write_text("VAR=group_file")

		process_env_file = tmp_path / "process.env"
		process_env_file.write_text("VAR=process_file")

		result = build_process_environment(
			system_env=False,
			global_env_files=False,
			group_env={"VAR": "group_dict"},
			group_env_file=group_env_file,
			process_env={"VAR": "process_dict"},
			process_env_file=process_env_file,
			override_env={"VAR": "override"},
		)

		# Override should win
		assert result["VAR"] == "override"

	def test_build_with_missing_env_file_raises_error(self):
		"""Test that missing process env file raises ValueError"""
		with pytest.raises(ValueError):
			build_process_environment(
				system_env=False,
				global_env_files=False,
				process_env_file="/nonexistent/file.env",
			)

	def test_build_with_missing_group_env_file_raises_error(self):
		"""Test that missing group env file raises ValueError"""
		with pytest.raises(ValueError):
			build_process_environment(
				system_env=False,
				global_env_files=False,
				group_env_file="/nonexistent/file.env",
			)

	def test_build_combines_all_sources(self, tmp_path: Path):
		"""Test that all sources are combined correctly"""
		process_env_file = tmp_path / "process.env"
		process_env_file.write_text("VAR3=value3")

		result = build_process_environment(
			system_env=False,
			global_env_files=False,
			group_env={"VAR1": "value1"},
			process_env={"VAR2": "value2"},
			process_env_file=process_env_file,
			override_env={"VAR4": "value4"},
		)

		assert result["VAR1"] == "value1"
		assert result["VAR2"] == "value2"
		assert result["VAR3"] == "value3"
		assert result["VAR4"] == "value4"

	def test_build_with_all_none_parameters(self):
		"""Test building with all parameters as None or False"""
		result = build_process_environment(
			system_env=False,
			global_env_files=False,
		)

		assert result == {}
