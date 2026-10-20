"""Remote host management and SSH transport"""

import shlex
import subprocess
from dataclasses import dataclass

from .state import RemoteInfo

DEFAULT_REMOTE_TIMEOUT = 10


@dataclass
class RemoteResult:
	returncode: int
	stdout: str
	stderr: str


def _build_ssh_command(remote: RemoteInfo) -> list[str]:
	cmd = ["ssh", "-o", f"BatchMode={'yes' if remote.batch_mode else 'no'}"]
	if remote.port is not None:
		cmd.extend(["-p", str(remote.port)])
	target = remote.host
	if remote.user is not None:
		target = f"{remote.user}@{remote.host}"
	cmd.extend(["--", target])
	return cmd


def run_remote_command(
	remote: RemoteInfo,
	command: list[str],
	timeout: int = DEFAULT_REMOTE_TIMEOUT,
) -> RemoteResult:
	ssh_cmd = _build_ssh_command(remote)
	ssh_cmd.append(shlex.join(command))

	try:
		result = subprocess.run(
			ssh_cmd,
			capture_output=True,
			text=True,
			check=False,
			timeout=timeout,
		)
		return RemoteResult(
			returncode=result.returncode,
			stdout=result.stdout,
			stderr=result.stderr,
		)
	except FileNotFoundError as e:
		return RemoteResult(
			returncode=127,
			stdout="",
			stderr=f"ssh binary not found: {e}",
		)
	except subprocess.TimeoutExpired:
		return RemoteResult(
			returncode=124,
			stdout="",
			stderr=f"SSH connection to {remote.host} timed out after {timeout}s",
		)


def run_remote_sentinel(
	remote: RemoteInfo,
	args: list[str],
	timeout: int = DEFAULT_REMOTE_TIMEOUT,
) -> RemoteResult:
	return run_remote_command(remote, ["sentinel", *args], timeout=timeout)


def format_remote(remote: RemoteInfo) -> str:
	if remote.user is not None:
		return f"{remote.user}@{remote.host}"
	return remote.host
