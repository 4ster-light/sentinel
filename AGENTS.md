# AGENTS.md - Sentinel

## Workflow

Nix flake is the main form of development and testing. Everything is
reproducible and isolated this way, always prefer to work within the flake
environment. Use `just` to run commands in this shell preferrably and only use
custom ones when necessary.

## Available Commands

Refer to `justfile` for all available commands. Source of truth is `justfile`,
`nix.flake` and `pyproject.toml`.

In order to see all available commands, run:

```bash
just help
```

## Verification

- Pytest is configured in `pyproject.toml` with `--cov-fail-under=80` and HTML
  coverage output.
- Use focused pytest targets when possible: file, class, method, or `-k`.
- Keep the usual order `fmt -> lint -> test` unless a task needs a different
  sequence.

> [!IMPORTANT]
> Any kind of submit that doesn't pass these checks in any way will be rejected.
> Always run `just fmt lint check` before submitting a PR.

## Project Shape

- Main code lives in `src/sentinel_core` and `src/sentinel_cli`.
- The CLI entry point is `sentinel_cli:app`.
- Tests mirror source layout under `tests/`.

## Style Constraints

- Python 3.14+ only: use `str | None`, `list[str]`, and full type hints.
- Ruff formatting is authoritative: tabs, double quotes, 120-character lines.
  Don't ever make formatting changes, just use ruff to fix them.
- Avoid unnecessary docstrings and trailing comments, prefer self documenting
  code and meaningfull concise explanation where needed.
- Catch specific exceptions; do not use bare `except`.
