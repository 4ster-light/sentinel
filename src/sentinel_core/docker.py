"""Container engine resolution and command builders for docker-backed processes"""

import re
import shlex
import shutil
from collections.abc import Sequence

ENGINE_CANDIDATES = ("docker", "podman")
STOP_GRACE_SECONDS = 10
_OPERATOR_TOKENS = frozenset({"&&", "||", ";", "|", "&"})
_ASSIGNMENT_PREFIX = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def resolve_engine(explicit: str | None = None) -> str:
	"""Return the container engine binary to use.

	An explicit choice wins and must name a known engine. Without one, the
	first engine found on PATH wins; docker is tried before podman.
	"""
	if explicit is not None:
		if explicit not in ENGINE_CANDIDATES:
			raise ValueError(f"unknown container engine {explicit!r}; use {' or '.join(ENGINE_CANDIDATES)}")
		return explicit
	for engine in ENGINE_CANDIDATES:
		if shutil.which(engine):
			return engine
	raise ValueError("no container engine found on PATH; install docker or podman, or pass --docker-engine")


def container_name(process_name: str) -> str:
	"""Stable container name for a process; cluster instances carry their index."""
	return f"sentinel-{process_name}"


def build_run_line(
	engine: str,
	process_name: str,
	image: str,
	cmd: str,
	ports: Sequence[str] = (),
	volumes: Sequence[str] = (),
) -> str:
	"""Build the stored run line: the command runs inside the image's container.

	A command without shell operators is prefixed with exec, so the workload
	becomes PID 1 and receives the engine stop signal directly. A compound
	command keeps the shell as PID 1. Every part is shell-quoted, so the line
	survives the host shell that starts it.
	"""
	parts = [engine, "run", "--rm", "--name", container_name(process_name)]
	for port in ports:
		parts.extend(["-p", port])
	for volume in volumes:
		parts.extend(["-v", volume])
	parts.append(image)
	parts.extend(["sh", "-c", _wrapped_command(cmd)])
	return " ".join(shlex.quote(part) for part in parts)


def build_stop_command(engine: str, process_name: str, *, force: bool = False) -> list[str]:
	"""Build the engine command that stops the process's container."""
	if force:
		return [engine, "kill", container_name(process_name)]
	return [engine, "stop", "-t", str(STOP_GRACE_SECONDS), container_name(process_name)]


def _needs_shell(cmd: str) -> bool:
	"""Report whether *cmd* is several statements rather than one command."""
	if "\n" in cmd:
		return True
	try:
		lexer = shlex.shlex(cmd, posix=True, punctuation_chars=True)
		lexer.whitespace_split = True
		tokens = list(lexer)
	except ValueError:
		return True
	if any(token in _OPERATOR_TOKENS for token in tokens):
		return True
	return bool(tokens) and _ASSIGNMENT_PREFIX.match(tokens[0]) is not None


def _wrapped_command(cmd: str) -> str:
	return cmd if _needs_shell(cmd) else f"exec {cmd}"
