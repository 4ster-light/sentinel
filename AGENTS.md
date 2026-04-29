# AGENTS.md - Sentinel

## Workflow

- Prefer `nix develop` for repo work.
- For one-off commands, prefer `nix run . -- <ARGS>`.
- `uv` is still supported, but only use it when Nix is not available.

## Common Commands

```bash
nix develop
nix run . -- --help
just test
just lint
just fmt
just check
just build
```

- `just test` runs pytest.
- `just lint` runs `ruff check --fix` and `ty check`.
- `just fmt` runs `ruff format`.
- `just check` runs `nix flake check`.
- `just serve` serves `htmlcov/` after tests generate coverage HTML.

## Verification

- Pytest is configured in `pyproject.toml` with `--cov-fail-under=80` and HTML coverage output.
- Use focused pytest targets when possible: file, class, method, or `-k`.
- Keep the usual order `fmt -> lint -> test` unless a task needs a different sequence.

## Project Shape

- Main code lives in `src/sentinel_core`, `src/sentinel_cli`, and `src/sentinel`.
- The CLI entry point is `sentinel_cli:app`.
- Tests mirror source layout under `tests/`.

## Style Constraints

- Python 3.14+ only: use `str | None`, `list[str]`, and full type hints.
- Ruff formatting is authoritative: tabs, double quotes, 120-character lines.
- Avoid unnecessary docstrings and trailing comments.
- Use relative imports inside the package.
- Catch specific exceptions; do not use bare `except`.
