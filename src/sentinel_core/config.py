"""Configuration file loading and the up reconciliation"""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .cluster import ScaleSpec, instance_name
from .dependencies import DependencyError
from .docker import build_run_line, resolve_engine
from .options import StartOptions
from .process import batch_start_processes, managed_process
from .state import DockerConfig, ProcessInfo, State


class ConfigError(ValueError):
	"""Raised for an invalid configuration file; the message cites the file and key."""


DISCOVERY_CANDIDATES = ("sentinel.toml", "sentinel.yaml", "sentinel.yml")

PROCESS_KEYS = frozenset(
	{
		"cmd",
		"restart",
		"user",
		"group",
		"env_file",
		"cwd",
		"health_http",
		"health_tcp",
		"health_interval",
		"health_timeout",
		"health_failures",
		"startup_timeout",
		"instances",
		"scale",
		"autoscale",
		"depends_on",
		"nice",
		"ionice",
		"docker",
	}
)
DOCKER_KEYS = frozenset({"image", "ports", "volumes", "engine"})


def discover_config(directory: Path | None = None) -> Path | None:
	"""Return the first known configuration file in *directory*, or None."""
	base = Path(directory) if directory is not None else Path.cwd()
	for candidate in DISCOVERY_CANDIDATES:
		path = base / candidate
		if path.is_file():
			return path
	return None


def load_config(path: Path) -> dict[str, StartOptions]:
	"""Parse and validate a configuration file into per-process start options."""
	path = Path(path)
	if not path.is_file():
		raise ConfigError(f"Configuration file '{path}' does not exist")
	data = _parse(path)
	if not isinstance(data, dict) or not isinstance(data.get("processes"), dict):
		raise ConfigError(f"{path}: must define a 'processes' table")
	for root_key in data:
		if root_key != "processes":
			raise ConfigError(f"{path}: unknown root key '{root_key}'")
	processes: dict[str, Any] = data["processes"]
	if not processes:
		raise ConfigError(f"{path}: 'processes' must define at least one process")

	specs: dict[str, StartOptions] = {}
	for name, table in processes.items():
		if not isinstance(table, dict):
			raise ConfigError(f"{path}: process '{name}' must be a table")
		options = _process_options(path, name, table)
		try:
			options.validate()
		except ValueError as e:
			raise ConfigError(f"{path}: process '{name}': {e}") from e
		specs[name] = options
	return specs


@dataclass
class UpReport:
	"""The reconciliation result of one up run."""

	started: list[ProcessInfo]
	failed: list[tuple[str, str]]
	skipped_running: list[str]
	conflicts: list[tuple[str, str]]
	groups_created: list[str]
	expected: list[str]


def run_up(state: State, path: Path, specs: dict[str, StartOptions]) -> UpReport:
	"""Start the file's processes: the missing ones, the stopped ones, nothing else."""
	for name, options in specs.items():
		for dependency in options.depends_on:
			target = specs.get(dependency)
			if target is not None:
				if target.scale is not None or target.instances > 1:
					raise ConfigError(f"{path}: process '{name}' cannot depend on the clustered process '{dependency}'")
			elif state.find_process_by_name(dependency) is None:
				raise ConfigError(
					f"{path}: process '{name}' depends on '{dependency}', which is neither in the file nor recorded"
				)

	starts: list[ProcessInfo] = []
	skipped_running: list[str] = []
	conflicts: list[tuple[str, str]] = []
	expected: list[str] = []
	for name, options in specs.items():
		scale_spec = options.scale_spec
		if scale_spec is None and options.instances > 1:
			scale_spec = ScaleSpec(options.instances, options.instances)
		instance_count = scale_spec.min_instances if scale_spec is not None else 1
		docker_config = options.docker_config
		engine = _resolved_engine(path, name, docker_config) if docker_config is not None else None
		for index in range(1, instance_count + 1):
			label = instance_name(name, index) if scale_spec is not None else name
			cmd = options.cmd
			instance_docker: DockerConfig | None = None
			if docker_config is not None and engine is not None:
				instance_docker = DockerConfig(
					image=docker_config.image,
					ports=list(docker_config.ports),
					volumes=list(docker_config.volumes),
					engine=engine,
				)
				cmd = build_run_line(
					engine,
					label,
					docker_config.image,
					options.cmd,
					ports=docker_config.ports,
					volumes=docker_config.volumes,
				)
			expected.append(label)
			existing = state.find_process_by_name(label)
			if existing is None:
				starts.append(
					_template(state.get_next_id(), label, name, index, options, scale_spec, cmd, instance_docker)
				)
				continue
			if existing.cmd != cmd:
				conflicts.append((label, existing.cmd))
			elif existing.stopped or managed_process(existing) is None:
				starts.append(existing)
			else:
				skipped_running.append(label)

	seen: set[str] = set()
	for label in expected:
		if label in seen:
			raise ConfigError(f"{path}: process '{label}' is defined twice")
		seen.add(label)

	groups_created: list[str] = []
	for options in specs.values():
		if options.group and state.get_group(options.group) is None:
			state.create_group(options.group)
			groups_created.append(options.group)

	try:
		started, failed = batch_start_processes(state, starts)
	except DependencyError as e:
		raise ConfigError(f"{path}: {e}") from e

	return UpReport(
		started=started,
		failed=[(info.name, error) for info, error in failed],
		skipped_running=skipped_running,
		conflicts=conflicts,
		groups_created=groups_created,
		expected=expected,
	)


def _parse(path: Path) -> Any:
	suffix = path.suffix.lower()
	if suffix == ".toml":
		try:
			return tomllib.loads(path.read_text(encoding="utf-8"))
		except tomllib.TOMLDecodeError as e:
			raise ConfigError(f"Invalid TOML in '{path}': {e}") from e
	if suffix in (".yaml", ".yml"):
		try:
			return yaml.safe_load(path.read_text(encoding="utf-8"))
		except yaml.YAMLError as e:
			raise ConfigError(f"Invalid YAML in '{path}': {e}") from e
	raise ConfigError(f"Unsupported configuration format '{suffix}'; use .toml, .yaml or .yml")


def _process_options(path: Path, name: str, table: dict[str, Any]) -> StartOptions:
	if "name" in table:
		raise _cited(path, name, "'name' is not allowed; the table key already names the process")
	for key in table:
		if key not in PROCESS_KEYS:
			raise _cited(path, name, f"unknown key '{key}'")
	if "cmd" not in table:
		raise _cited(path, name, "'cmd' is required")

	image, ports, volumes, engine = (
		_docker_options(path, name, table["docker"]) if "docker" in table else (None, [], [], None)
	)
	return StartOptions(
		cmd=_command(path, name, table),
		name=name,
		restart=_boolean(path, name, table, "restart"),
		user=_optional_string(path, name, table, "user"),
		group=_optional_string(path, name, table, "group"),
		env_file=_optional_string(path, name, table, "env_file"),
		cwd=_optional_string(path, name, table, "cwd"),
		health_http=_optional_string(path, name, table, "health_http"),
		health_tcp=_optional_string(path, name, table, "health_tcp"),
		health_interval=_number(path, name, table, "health_interval", default=30.0),
		health_timeout=_number(path, name, table, "health_timeout", default=3.0),
		health_failures=_integer(path, name, table, "health_failures", default=3),
		startup_timeout_seconds=_optional_number(path, name, table, "startup_timeout"),
		instances=_integer(path, name, table, "instances", default=1),
		scale=_optional_string(path, name, table, "scale"),
		autoscale=_string_list(path, name, table, "autoscale"),
		depends_on=_string_list(path, name, table, "depends_on"),
		nice=_optional_integer(path, name, table, "nice"),
		ionice=_optional_string(path, name, table, "ionice"),
		docker_image=image,
		docker_ports=ports,
		docker_volumes=volumes,
		docker_engine=engine,
	)


def _docker_options(path: Path, name: str, table: Any) -> tuple[str, list[str], list[str], str | None]:
	if not isinstance(table, dict):
		raise _cited(path, name, "'docker' must be a table")
	for key in table:
		if key not in DOCKER_KEYS:
			raise _cited(path, name, f"unknown docker key '{key}'")
	if "image" not in table:
		raise _cited(path, name, "'docker.image' is required")
	image = table["image"]
	if not isinstance(image, str) or not image.strip():
		raise _cited(path, name, "'docker.image' must be a string")
	ports = table.get("ports")
	if ports is not None and not _is_string_list(ports):
		raise _cited(path, name, "'docker.ports' must be a list of strings")
	volumes = table.get("volumes")
	if volumes is not None and not _is_string_list(volumes):
		raise _cited(path, name, "'docker.volumes' must be a list of strings")
	engine = table.get("engine")
	if engine is not None and not isinstance(engine, str):
		raise _cited(path, name, "'docker.engine' must be a string")
	return image, list(ports or []), list(volumes or []), engine


def _command(path: Path, name: str, table: dict[str, Any]) -> str:
	value = table["cmd"]
	if not isinstance(value, str):
		raise _cited(path, name, "'cmd' must be a string")
	if not value.strip():
		raise _cited(path, name, "'cmd' cannot be empty")
	return value


def _optional_string(path: Path, name: str, table: dict[str, Any], key: str) -> str | None:
	value = table.get(key)
	if value is None:
		return None
	if not isinstance(value, str):
		raise _cited(path, name, f"'{key}' must be a string")
	return value


def _boolean(path: Path, name: str, table: dict[str, Any], key: str) -> bool:
	value = table.get(key)
	if value is None:
		return False
	if not isinstance(value, bool):
		raise _cited(path, name, f"'{key}' must be a boolean")
	return value


def _integer(path: Path, name: str, table: dict[str, Any], key: str, default: int) -> int:
	value = _optional_integer(path, name, table, key)
	return default if value is None else value


def _optional_integer(path: Path, name: str, table: dict[str, Any], key: str) -> int | None:
	value = table.get(key)
	if value is None:
		return None
	if isinstance(value, bool) or not isinstance(value, int):
		raise _cited(path, name, f"'{key}' must be an integer")
	return value


def _number(path: Path, name: str, table: dict[str, Any], key: str, default: float) -> float:
	value = _optional_number(path, name, table, key)
	return default if value is None else value


def _optional_number(path: Path, name: str, table: dict[str, Any], key: str) -> float | None:
	value = table.get(key)
	if value is None:
		return None
	if isinstance(value, bool) or not isinstance(value, (int, float)):
		raise _cited(path, name, f"'{key}' must be a number")
	return value


def _string_list(path: Path, name: str, table: dict[str, Any], key: str) -> list[str]:
	value = table.get(key)
	if value is None:
		return []
	if not _is_string_list(value):
		raise _cited(path, name, f"'{key}' must be a list of strings")
	return list(value)


def _is_string_list(value: Any) -> bool:
	return isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value)


def _cited(path: Path, name: str, detail: str) -> ConfigError:
	return ConfigError(f"{path}: process '{name}': {detail}")


def _resolved_engine(path: Path, name: str, docker: DockerConfig) -> str:
	try:
		return resolve_engine(docker.engine)
	except ValueError as e:
		raise ConfigError(f"{path}: process '{name}': {e}") from e


def _template(
	process_id: int,
	label: str,
	name: str,
	index: int,
	options: StartOptions,
	scale_spec: ScaleSpec | None,
	cmd: str,
	instance_docker: DockerConfig | None,
) -> ProcessInfo:
	ionice_ioclass, ionice_value = options.ionice_spec()
	cluster_mode = scale_spec is not None
	return ProcessInfo(
		id=process_id,
		pid=0,
		name=label,
		cmd=cmd,
		cwd=str(Path(options.cwd or Path.cwd()).resolve()),
		restart=options.restart,
		started_at="",
		stdout_log="",
		stderr_log="",
		user=options.user,
		group=options.group,
		depends_on=list(options.depends_on),
		cluster=name if cluster_mode else None,
		cluster_index=index if cluster_mode else None,
		cluster_min=scale_spec.min_instances if scale_spec is not None else None,
		cluster_max=scale_spec.max_instances if scale_spec is not None else None,
		autoscale=options.autoscale_config,
		env_file=options.env_file,
		docker=instance_docker,
		health_check=options.health_check,
		startup_timeout_seconds=options.startup_timeout_seconds,
		nice=options.nice,
		ionice_ioclass=ionice_ioclass,
		ionice_value=ionice_value,
	)
