# Sentinel Architecture

This document maps the codebase for contributors. For usage, see the
[README](README.md); for workflow and tooling, see
[CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md).

## Package layout

Two packages live under `src/`:

- **`sentinel_core`** — domain logic, no CLI dependencies. Importable and
  usable as a library.
- **`sentinel_cli`** — Typer/Rich presentation layer over `sentinel_core`.

The rule of thumb: anything that decides *what happens* belongs in
`sentinel_core`; anything that decides *how it looks or how it is phrased*
belongs in `sentinel_cli`.

### sentinel_core modules

| Module | Responsibility |
| ------ | --------------- |
| `models.py` | Dataclasses persisted in `state.json` (`ProcessInfo`, `GroupInfo`, `PortInfo`, `RemoteInfo`, `HealthCheckConfig`) |
| `state_store.py` | Owns the `state.json` file: parsing, validation, atomic writes, and advisory locking |
| `registries.py` | One registry per domain section (processes, ports, groups, remotes), each mutating the store under its lock |
| `state.py` | `State` facade over the registries (stable API) plus module constants and `get_log_paths` |
| `process.py` | Spawning, stopping (whole process group), restarting, priority, and batch operations |
| `restart_monitor.py` | The restart engine: a single scan pass shared by the daemon loop and the lazy CLI check |
| `health.py` | HTTP/TCP health probes and scheduling decisions |
| `logs.py` | Log rotation, tailing, following, clearing |
| `env.py` | `.env` loading and environment merge precedence |
| `metrics.py` | Metrics collection and table/JSON export |
| `options.py` | `StartOptions` — validated start parameters, shared by CLI and tests |
| `format.py` | Human-readable uptime/memory formatting shared by CLI and metrics |
| `remote.py` | SSH transport for remote management |

### sentinel_cli modules

One module per command group (`main`, `group`, `port`, `daemon`, `metrics`,
`remote`, `startup`), each registering a Typer sub-app in `__init__.py`.
`common.py` holds shared helpers such as `load_state()` (constructs the state
and surfaces corruption warnings).

## State storage

Everything persists in `~/.sentinel/` (override with the `SENTINEL_STATE_DIR`
environment variable):

- `state.json` — processes, ports, groups, remotes, and `next_id`. Written
  atomically (temp file + rename).
- `state.json.lock` — advisory `flock` held by every read-modify-write
  mutation, so the daemon and CLI commands cannot lose each other's changes.
- `logs/` — per-process stdout/stderr logs with size-based rotation
  (10MB, 3 backups).
- `daemon.pid` / `daemon.log` — restart monitor PID file and rotating log.
- `state.json.corrupt-<timestamp>` — backup of an unparseable state file;
  Sentinel warns and starts from empty state rather than failing.

## Restart model

Two code paths share one engine (`check_and_restart_processes` in
`restart_monitor.py`):

- **Daemon mode**: `sentinel daemon start` spawns a detached process that
  scans every 5 seconds, runs health checks, restarts crash-flagged
  processes, and cleans up dead ones.
- **Lazy mode**: read-oriented CLI commands (`list`, `status`) run one scan
  pass inline, so restarts still happen without the daemon.

## Process lifecycle

Processes are spawned with `shell=True` and `start_new_session=True`, which
makes each managed process the leader of its own process group. `stop`
signals the entire group so children of compound commands
(`cmd1 && cmd2`, background jobs) die with the leader. Exit codes: `0`
success, `1` handled failure; `sentinel remote` passes the remote exit code
through.

## Adding a command

1. Implement the behavior in `sentinel_core` (with unit tests).
2. Add a thin Typer command in `sentinel_cli` that validates input, calls the
   core function, and prints the result.
3. Register the command (sub-apps in `__init__.py`, plain commands via
   `register_main_commands`).
4. Add CLI tests under `tests/cli/` mirroring the core tests under
   `tests/core/`.
5. Document it in the README and run `nix develop -c just c`.
