# Contributing to Sentinel

Thank you for your interest in contributing! This document outlines the
development workflow and tools we use.

## Development Setup

**Nix** is the recommended way to develop _Sentinel_ because it provides a
reproducible environment and is the main build tool of the project.

Set up the development environment with:

```bash
nix develop
```

From there, use the helper commands in `justfile` (to see all available commands
run `just -l`).

> [!NOTE]
> If you prefer not to use Nix, standalone `uv` is still a valid development
> setup (but isn't a reproducible way to validate submits since the system isn't
> encapsulated, therefore it will be treated as pending of validation), run the
> following to set up a virtual environment and install dependencies:
>
> ```bash
> uv sync
> ```

## Tools & Workflow

### Testing with pytest

Run the test suite:

```bash
just t
```

Tests are configured in `pyproject.toml` with a minimum coverage threshold of
85%. An HTML coverage report is automatically generated after each test run.

#### View coverage report

After running tests, view the coverage report in your browser:

```bash
just s
```

Then open <http://localhost:8000> in your browser to view the HTML coverage
report.

### Code Quality Checks

This project follows a _TDD (Test-Driven Development)_ workflow. Tests are the
source of truth for code correctness and expected behaviour. Therefore for a
build to be considered valid, all tests must pass, and these must have a minimum
coverage threshold of 85% (this is hardcoded in the pytest flags found in
`pyproject.toml` so tests will fail otherwise, so will do builds since they
execute a check phase as well).

We use three main tools for code quality. Run them together or individually:

**Format all code:**

```bash
just fmt
```

**Lint and type-check:**

```bash
just lint
```

**Run all checks together:**

```bash
just c
```

## Branching & Pull Requests

`main` is the integration branch: work on a topic branch and open a pull
request instead of pushing directly. Direct pushes to `main` are acceptable
for minor, inconsequential changes, but that should not become the norm.

Name branches `<label>/<title>` using the same labels as conventional commits,
with a short kebab-case title:

- `feat/port-allocation`
- `fix/restart-loop`
- `docs/branch-workflow`
- `chore/nix-update`

Common labels are `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`,
`ci`, `chore`, `style` and `revert`. Dependabot branches keep their generated
names.

Open pull requests against `main` with a conventional-commit title. CI runs the
full gate on pull requests and merge queue entries (`merge_group`), plus manual
`workflow_dispatch`; it intentionally does not run on every push to `main`, so
merging a validated PR does not trigger a duplicate run. If you do push
directly to `main`, run `just c` locally first.

## Before Submitting

Make sure your changes pass all checks and tests:

```bash
just c
```

Checks also run automatically via GitHub Actions on pull requests and merge
queue entries, using the same Nix environment described above.

Any new features or bug fixes should be accompanied by tests. If you are adding
a new feature, please include tests that cover the new functionality. All
mentioned checks should pass before submitting.

> [!IMPORTANT]
> This project follows
> [conventional commits](https://gist.github.com/qoomon/5dfcdf8eec66a051ecd85625518cfd13).

## Project Structure

```text
src/                # Source code of the different packages
  sentinel_core/    # Core library (domain logic)
  sentinel_cli/     # CLI interface
tests/              # Test files mirroring src structure
justfile            # Development task runner
flake.nix           # Nix flake configuration
pyproject.toml      # Project configuration
ARCHITECTURE.md     # Codebase map for contributors
ROADMAP.md          # Release plan and feature goals
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for how the pieces fit together before
diving into the code.

## Releasing

Releases are cut from `main` with a signed tag; the tag drives every channel.

1. Refresh the flake inputs and merge the resulting pull request
   (`nix flake update`; Dependabot also opens these monthly).
2. Bump the version in `pyproject.toml`, the `Version:` line in
   `packaging/fedora/sentinel-pm.spec`, and add a spec changelog entry.
3. Run `just release-check` (tag, project version and spec must agree) and
   `just c`.
4. Commit as `chore(release): vX.Y.Z`, then create the annotated tag with an
   explicit message so no editor is needed:
   `git -c core.editor=true tag -a vX.Y.Z -m "vX.Y.Z: summary"`, and push it
   with `git push origin vX.Y.Z`.
5. The `Release` workflow runs the gate, publishes to TestPyPI and PyPI
   through OIDC trusted publishing, and creates the GitHub release with the
   sdist and wheel attached.
6. Rebuild the COPR package from the tag:

   ```bash
   cd packaging/fedora
   make srpm     # rpmbuild comes from `nix shell nixpkgs#rpm`
   uvx copr-cli build sentinel-pm sentinel-pm-X.Y.Z-1.src.rpm
   ```

The floors in `[project.dependencies]` are the verified minimums the Fedora
chroots can satisfy; `just fedora-floors` checks them against fedora-44,
fedora-45 and rawhide. Dependabot is lockfile-only for uv, so it keeps
`uv.lock` current without moving those floors.

## Questions?

Feel free to open an issue if you have any questions or need clarification! Even
if you are not sure if your contribution is appropriate, we welcome respectful
discussions and feedback.
