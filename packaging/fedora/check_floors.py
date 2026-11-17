"""Verify that runtime dependency floors are satisfiable in the Fedora chroots.

The RPM is built with %pyproject_buildrequires -r, so every requirement in
[project.dependencies] resolves from the distribution rather than from PyPI.
A floor above what a supported chroot ships breaks the COPR build, which this
check reports before a release instead of after it.
"""

import json
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import InvalidVersion, Version

# COPR chroot name -> mdapi release name
CHROOTS = {"fedora-44": "f44", "fedora-45": "f45", "rawhide": "rawhide"}
MDAPI = "https://mdapi.fedoraproject.org/{release}/pkg/python3-{name}"
TIMEOUT_SECONDS = 20
PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"
LOWER_BOUND_OPERATORS = (">=", ">", "==", "===", "~=")


def runtime_requirements() -> list[Requirement]:
	project = tomllib.loads(PYPROJECT.read_text())
	return [Requirement(raw) for raw in project["project"]["dependencies"]]


def fedora_version(chroot: str, name: str) -> Version | None:
	"""Version of python3-<name> in a chroot, or None when it is not packaged."""
	release = CHROOTS[chroot]
	url = MDAPI.format(release=release, name=name.lower())
	try:
		with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:
			payload = json.load(response)
	except urllib.error.HTTPError as error:
		if error.code in (400, 404):
			return None
		raise
	try:
		epoch = int(payload.get("epoch") or 0)
		version = payload["version"]
	except (KeyError, TypeError, ValueError) as error:
		raise ValueError(f"Unexpected mdapi payload for {name} in {chroot}: {payload!r}") from error
	return Version(f"{epoch}!{version}" if epoch else version)


def main() -> int:
	failures: list[str] = []
	try:
		for requirement in runtime_requirements():
			for chroot in CHROOTS:
				version = fedora_version(chroot, requirement.name)
				if version is None:
					failures.append(f"{requirement.name}: not packaged in {chroot}")
					continue
				for specifier in requirement.specifier:
					if specifier.operator not in LOWER_BOUND_OPERATORS:
						continue
					try:
						floor = Version(specifier.version)
					except InvalidVersion:
						continue
					if version < floor:
						failures.append(f"{requirement.name}{specifier}: {chroot} ships {version}")
	except urllib.error.URLError as error:
		print(f"Cannot query mdapi: {error}", file=sys.stderr)
		return 2

	if failures:
		print("Runtime dependency floors are not satisfiable from Fedora:")
		for failure in sorted(set(failures)):
			print(f"  {failure}")
		return 1

	print(f"Runtime floors satisfied in {', '.join(CHROOTS)}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
