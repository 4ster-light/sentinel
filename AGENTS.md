# AGENTS.md - Sentinel

## Workflow

Nix flake is the main form of development and testing. Everything is
reproducible and isolated this way, always prefer to work within the flake
environment. Use `nix` and `just` to run commands in this shell preferrably and
only use custom ones when necessary.

## Available Commands

Refer to `justfile` for all available commands. Source of truth is `justfile`,
`flake.nix` and `pyproject.toml`.

In order to see all available commands, run:

```bash
nix develop -c just -l
```

If nix isn't available, you can also run `just -l`, but if just isn't available
either read the justfile directly and try to work with what's available in the
system as long as it doesn't become a roadblocker.

> [!IMPORTANT]
> Any kind of submit that doesn't pass these checks in any way will be rejected:
>
> - Always run `nix develop -c just c` before submitting a PR.
> - Use focused pytest targets when possible with
>   `nix develop -c just test <TEST_STRING>`: file, class, method, or `-k`.

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
