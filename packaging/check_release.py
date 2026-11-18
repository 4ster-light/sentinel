"""Check that the release tag, the project version and the RPM spec agree."""

import os
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "packaging/fedora/sentinel-pm.spec"


def main() -> int:
	version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
	match = re.search(r"^Version:\s*(\S+)", SPEC.read_text(), re.MULTILINE)
	spec_version = match.group(1) if match else None

	problems: list[str] = []
	if spec_version != version:
		problems.append(f"spec Version is {spec_version or 'missing'}, pyproject has {version}")

	tag = os.environ.get("GITHUB_REF_NAME", "")
	if tag.startswith("v") and tag[1:] != version:
		problems.append(f"tag {tag} does not match pyproject version {version}")

	if problems:
		print("Release versions disagree:")
		for problem in problems:
			print(f"  {problem}")
		return 1

	print(f"Release versions agree on {version}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
