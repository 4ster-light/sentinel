# AGENTS.md — Sentinel

Guidance for AI coding agents working on Sentinel. See
[ARCHITECTURE.md](ARCHITECTURE.md) for the codebase map and
[CONTRIBUTING.md](CONTRIBUTING.md) for the human-facing workflow.

## Nix-first workflow

The Nix flake is the single source of truth for development, testing and CI.
It pins Python 3.14, `uv`, `ruff`, `ty`, `just`, `pytest` and the runtime
dependencies, so every command is reproducible and isolated.

- Run everything inside the flake: `nix develop -c <command>`.
- Prefer `nix` + `just` recipes over ad-hoc commands.
- `nix flake check` builds the package, runs a smoke test and executes the
  pytest check phase with a fresh `HOME` and `TMPDIR`.
- Only fall back to system tooling if Nix is genuinely unavailable and it is
  blocking progress. A non-Nix result is treated as unvalidated.

Entering the shell creates `.venv` automatically and points `UV_PROJECT_ENVIRONMENT`
at it:

```bash
nix develop
```

## Commands

`justfile`, `flake.nix` and `pyproject.toml` are authoritative. List recipes
with `nix develop -c just -l`.

| Command                    | Purpose                                                      |
| -------------------------- | ------------------------------------------------------------ |
| `just c` / `just check`    | Full gate: tests, lint, format check, `nix flake check`      |
| `just t` / `just test-all` | Full pytest run with coverage (85% floor)                    |
| `just test <TARGET>`       | Focused pytest without coverage: file, class, method or `-k` |
| `just lint`                | `ruff check` + `ty check`                                    |
| `just fmt`                 | `ruff format` (write)                                        |
| `just b` / `just build`    | `nix build`                                                  |
| `just s` / `just serve`    | Serve the HTML coverage report at :8000                      |

## Before submitting

> [!IMPORTANT]
> Submissions that fail any of these are rejected:
>
> - Always run `nix develop -c just c` before opening a PR.
> - Use focused targets while iterating: `nix develop -c just test <TEST_STRING>`,
>   where `<TEST_STRING>` is a file, class, method or `-k` expression.
> - Follow [conventional commits](https://gist.github.com/qoomon/5dfcdf8eec66a051ecd85625518cfd13)
>   (`feat(scope): ...`, `fix(core): ...`, `docs: ...`).
> - New behavior and bug fixes require tests. Coverage is measured on
>   `sentinel_core` and `sentinel_cli` and must stay at or above 85%.

## Project shape

- `src/sentinel_core` — domain logic with no CLI dependencies, usable as a library.
- `src/sentinel_cli` — Typer/Rich presentation layer over the core.
- CLI entry point: `sentinel_cli:app` (installed as `sentinel`).
- Tests mirror the source layout under `tests/` (`tests/core`, `tests/cli`).
- State lives in `~/.sentinel/`; override with `SENTINEL_STATE_DIR`. Tests set
  this and other globals via the autouse `isolated_runtime` fixture in
  `tests/conftest.py`.
- Rule of thumb: *what happens* belongs in `sentinel_core`; *how it looks or is
  phrased* belongs in `sentinel_cli`.

## Style constraints

- Python 3.14+ only: use `str | None`, `list[str]`, and full type hints.
- Ruff formatting is authoritative: tabs, double quotes, 120-character lines.
  Never hand-format; run `just fmt` and let Ruff decide.
- Avoid unnecessary docstrings and trailing comments; prefer self-documenting
  code with concise explanations only where the intent is non-obvious.
- Catch specific exceptions; never use a bare `except`.
