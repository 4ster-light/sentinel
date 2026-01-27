"""Environment variable loading and management utilities"""

import os
from pathlib import Path

from dotenv import dotenv_values


def load_env_file(file_path: str | Path) -> dict[str, str]:
	path = Path(file_path)

	if not path.exists():
		raise FileNotFoundError(f"Environment file not found: {path}")

	if not path.is_file():
		raise ValueError(f"Environment path is not a file: {path}")

	try:
		env_vars = dotenv_values(path)
		return {k: v for k, v in env_vars.items() if v is not None}
	except Exception as e:
		raise ValueError(f"Failed to load environment file {path}: {e}")


def find_global_env_files() -> list[Path]:
	env_files: list[Path] = []

	# Check Sentinel-specific .env
	sentinel_env = Path.home() / ".sentinel" / ".env"
	if sentinel_env.exists():
		env_files.append(sentinel_env)

	# Check current directory .env
	cwd_env = Path.cwd() / ".env"
	if cwd_env.exists():
		env_files.append(cwd_env)

	return env_files


def merge_environments(*env_dicts: dict[str, str] | None) -> dict[str, str]:
	result: dict[str, str] = {}

	for env_dict in env_dicts:
		if env_dict is not None:
			result.update(env_dict)

	return result


def build_process_environment(
	system_env: bool = True,
	global_env_files: bool = True,
	group_env: dict[str, str] | None = None,
	group_env_file: str | Path | None = None,
	process_env: dict[str, str] | None = None,
	process_env_file: str | Path | None = None,
	override_env: dict[str, str] | None = None,
) -> dict[str, str]:
	"""
	Merge order (lowest to highest priority):
	1. System environment (if system_env=True)
	2. Global ~/.sentinel/.env and ./.env files (if global_env_files=True)
	3. Group-level env vars dict
	4. Group env file (if specified)
	5. Process env vars dict
	6. Process env file (if specified)
	7. Override env vars (highest priority)
	"""

	env_dicts: list[dict[str, str] | None] = []

	# Start with system environment if requested
	if system_env:
		env_dicts.append(os.environ.copy())

	# Add global env files
	if global_env_files:
		for env_file in find_global_env_files():
			try:
				env_dicts.append(load_env_file(env_file))
			except (FileNotFoundError, ValueError):
				# Log warning but continue (graceful)
				pass

	# Add group-level env
	if group_env:
		env_dicts.append(group_env)

	# Add group env file
	if group_env_file:
		try:
			env_dicts.append(load_env_file(group_env_file))
		except (FileNotFoundError, ValueError) as e:
			raise ValueError(f"Cannot load group env file: {e}")

	# Add process-level env
	if process_env:
		env_dicts.append(process_env)

	# Add process env file
	if process_env_file:
		try:
			env_dicts.append(load_env_file(process_env_file))
		except (FileNotFoundError, ValueError) as e:
			raise ValueError(f"Cannot load process env file: {e}")

	# Add override env (highest priority)
	if override_env:
		env_dicts.append(override_env)

	return merge_environments(*env_dicts)
