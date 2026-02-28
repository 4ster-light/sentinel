# AGENTS.md - Development Guide for AI Agents

This document provides essential guidelines for AI agents operating on the
Sentinel codebase. Focus on self-documenting, readable code with modern Python
practices and zero hidden state.

## Quick Commands

### Running Tests

```bash
# Run all tests with coverage
uv run pytest

# Run a single test file
uv run pytest tests/test_process.py

# Run a single test class
uv run pytest tests/test_process.py::TestStartProcess

# Run a single test method
uv run pytest tests/test_process.py::TestStartProcess::test_start_simple_process

# Run tests matching a pattern (most useful!)
uv run pytest -k "restart"

# Run with verbose output
uv run pytest -v tests/test_state.py

# Run specific tests and show output
uv run pytest -s tests/test_process.py::TestStartProcess::test_start_simple_process
```

### Code Quality (Run Before Committing)

```bash
# Format code (tabs, 120-char line length, double quotes)
uv run ruff format

# Lint and fix issues
uv run ruff check --fix

# Type check with Pyright
uv run ty check

# All checks at once
uv run ruff format && uv run ruff check --fix && uv run ty check
```

## Code Style Guidelines

### Self-Documenting Code First

**NO unnecessary docstrings**. Code should be clear without them:

```python
# ✗ BAD: Redundant docstring
def is_running() -> bool:
    """Check if the monitor is running."""
    return self._running

# ✓ GOOD: Name + type hint = self-documenting
def is_running() -> bool:
    return self._running

# ✓ GOOD: Only docstring when clarifying why or non-obvious behavior
def get_restart_monitor() -> RestartMonitor:
    """Get or create the restart monitor instance."""
    return _singleton.get()
```

**Use explicit variable names** that reveal intent:

```python
# ✗ BAD
procs = state.processes.values()
for p in procs:
    if not psutil.pid_exists(p.pid):
        cleanup(p)

# ✓ GOOD: Names tell the story
processes_to_cleanup: list[ProcessInfo] = []
for process_info in state.processes.values():
    if not psutil.pid_exists(process_info.pid):
        processes_to_cleanup.append(process_info)
```

### Formatting & Structure

- **Line length**: 120 characters (Ruff configured)
- **Indentation**: Tabs, not spaces
- **Quotes**: Double quotes only (`"` not `'`)
- **No trailing comments**: Use clear code instead
  - ✗ `x += 1  # Increment x`
  - ✓ `next_id = current_id + 1`

### Modern Python Type Hints (3.14+)

- **All parameters** must have type hints
- **All return types** are mandatory (including `-> None`)
- Use **new union syntax**: `str | None` NOT `Optional[str]`
- Use **generic syntax**: `list[str]`, `dict[str, int]` NOT `List`, `Dict`
- Avoid `Any` except in exceptional cases (with TODO comment)
- Use `|` for unions: `int | str | None`

```python
# ✗ BAD: Missing hints, old syntax
def process_items(items, config=None):
    return [item * 2 for item in items]

# ✓ GOOD: Explicit, modern syntax
def process_items(items: list[int], config: dict[str, str] | None = None) -> list[int]:
    return [item * 2 for item in items]
```

### Naming Conventions

- **Functions/variables**: `snake_case`
- **Classes**: `PascalCase`
- **Constants**: `UPPER_SNAKE_CASE` (at module level, immutable)
- **Private/internal**: `_leading_underscore` for methods/variables
- **Descriptive names**: Always use full words, never abbreviate
  - ✗ `p_info`, `s_dir`, `cfg`
  - ✓ `process_info`, `state_dir`, `config`

### Imports (Strict Ordering)

Group by: **stdlib** → **third-party** → **local**, alphabetical within each
group:

```python
# ✓ GOOD: Correct order
from datetime import datetime
from pathlib import Path

import psutil
import typer
from rich.console import Console

from .process import start_process
from .state import ProcessInfo, State
```

Rules:

- Use relative imports: `from .module import func` not
  `from sentinel.module import func`
- Import from specific modules, not packages:
  `from .cli.main import register_commands`
- One import per line (except `from x import a, b, c`)

### Avoiding Hidden State & Side Effects

**NO global keyword** — use dependency injection or context managers:

```python
# ✗ BAD: Hidden global state
_monitor = None

def get_monitor():
    global _monitor
    if _monitor is None:
        _monitor = RestartMonitor()
    return _monitor

# ✓ GOOD: Context manager pattern
@contextmanager
def restart_monitor(check_interval: float = 5.0) -> Generator[RestartMonitor, None, None]:
    monitor = RestartMonitor(check_interval)
    monitor.start()
    try:
        yield monitor
    finally:
        monitor.stop()

# Usage
with restart_monitor(check_interval=5.0) as monitor:
    monitor.set_restart_callback(callback)
    # use monitor
```

**Pass state explicitly** instead of relying on implicit globals:

```python
# ✗ BAD: Implicit dependency on global STATE
def add_process(name: str) -> ProcessInfo:
    info = ProcessInfo(...)
    STATE.add_process(info)  # Where does STATE come from?
    return info

# ✓ GOOD: Explicit parameter
def add_process(state: State, name: str) -> ProcessInfo:
    info = ProcessInfo(...)
    state.add_process(info)
    return info
```

### Error Handling

- Raise `ValueError` for invalid inputs/state (application errors)
- Raise `FileNotFoundError`, `PermissionError` for I/O issues
- Let process-level exceptions propagate when appropriate
- Catch specific exceptions, never bare `except:`
- Log exceptions with context before re-raising

```python
# ✗ BAD: Bare except
try:
    proc = psutil.Process(pid)
except:
    return False

# ✓ GOOD: Specific + logged
try:
    proc = psutil.Process(pid)
    return proc.status() != psutil.STATUS_ZOMBIE
except (psutil.NoSuchProcess, psutil.AccessDenied):
    return False
```

In CLI commands, use Rich formatting:

```python
try:
    result = do_something()
    console.print(f"[green]✓[/] Success: {result}")
except ValueError as e:
    console.print(f"[red]✗[/] {e}")
    raise typer.Exit(1)
```

## Testing Guidelines

**Test structure** mirrors source code:

```txt
src/sentinel/process.py     →  tests/test_process.py
src/sentinel/state.py       →  tests/test_state.py
src/sentinel/cli/main.py    →  tests/test_cli_main.py
```

**Naming**:

- Test files: `test_*.py`
- Test classes: `TestXxx` (e.g., `TestStartProcess`)
- Test methods: `test_*` (descriptive names)
- Fixtures: in `conftest.py` (available: `state`, `temp_state_dir`)

**Minimum coverage**: 80% enforced by `--cov-fail-under=80`

**Pattern**:

```python
class TestFeature:
    def test_happy_path(self, state: State) -> None:
        """Descriptive name: what is being tested and expected outcome."""
        info = start_process(state, "sleep 10", name="test")
        assert info.name == "test"
        assert psutil.pid_exists(info.pid)
        
        proc = psutil.Process(info.pid)
        proc.terminate()
        proc.wait()
    
    def test_error_case(self, state: State) -> None:
        """Test error handling."""
        with pytest.raises(ValueError, match="already exists"):
            start_process(state, "sleep 10", name="test")
            start_process(state, "sleep 20", name="test")
```

**Always clean up processes**:

```python
proc = psutil.Process(info.pid)
proc.terminate()
proc.wait()  # ← Critical: always wait for clean shutdown
```

## Architecture Notes

### State Management (state.py)

- `ProcessInfo`: dataclass holding process metadata
- `State`: JSON-backed registry in `~/.sentinel/state.json`
- Thread-safe access via locks
- Methods: `add_process()`, `remove_process()`, `find_process_by_name()`

### Process Lifecycle (process.py)

- `start_process()`: Spawns subprocess, sets up logging, returns ProcessInfo
- `stop_process()`: SIGTERM → wait 5s → SIGKILL
- `restart_process()`: stop + start pattern
- `get_process_status()`: Checks if PID still running
- Logs route to `~/.sentinel/logs/{name}.{stdout,stderr}`

### CLI Structure (cli/)

- Commands registered via `register_*_commands()` functions
- Uses `typer.Typer` for command groups
- Rich console for colored output (✓ green, ✗ red, ⚠ yellow)
- Annotated types for options: `Annotated[bool, typer.Option("--force")]`

### Restart Monitor (restart_monitor.py)

- Daemon thread monitoring processes with `restart=True`
- Check interval: 5 seconds (configurable)
- Context manager pattern for safe lifecycle management
- Thread-safe via internal locks
- Full logging for operational visibility

## Common Patterns

### Dataclass with Serialization

```python
@dataclass
class ProcessInfo:
    id: int
    name: str
    pid: int
    env: dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "pid": self.pid,
            "env": self.env,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProcessInfo:
        return cls(
            id=data["id"],
            name=data["name"],
            pid=data["pid"],
            env=data.get("env", {}),
        )
```

### Type-Hinted Callable

```python
from typing import Callable

callback: Callable[[ProcessInfo], None] | None = None

if callback:
    callback(new_info)
```

### Context Manager for Cleanup

```python
from contextlib import contextmanager

@contextmanager
def open_log_files(name: str):
    stdout_file = open(f"logs/{name}.stdout", "a")
    stderr_file = open(f"logs/{name}.stderr", "a")
    try:
        yield stdout_file, stderr_file
    finally:
        stdout_file.close()
        stderr_file.close()
```

## Key Dependencies

- **typer**: CLI framework with automatic help generation
- **rich**: Terminal formatting (colors, tables, progress bars)
- **psutil**: Process monitoring (PIDs, status, signals)
- **pytest**: Test framework with fixtures
- **ruff**: Fast linting + formatting (replaces Black + flake8)
- **ty (Pyright)**: Static type checker

## Commit Message Convention

[Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` new feature
- `fix:` bug fix
- `refactor:` restructuring (no behavior change)
- `test:` test additions/fixes
- `docs:` documentation only
- `chore:` deps, tooling, config

Example: `fix: eliminate global keyword in restart monitor`

## Critical Anti-Patterns

1. **Global variables with `global` keyword** → Use classes instead
2. **Bare `except:` or `except Exception:`** → Catch specific exceptions
3. **Mutable default arguments** → Use `field(default_factory=dict)`
4. **Comments explaining code** → Refactor code to be self-explanatory
5. **Optional type** → Use `T | None` instead
6. **Spaces for indentation** → Always use tabs
7. **Single quotes** → Always use double quotes
