# Contributing to Sentinel

Thank you for your interest in contributing! This document outlines the
development workflow and tools we use.

## Development Setup

We use [uv](https://astral.sh/uv) for fast and reliable Python dependency
management. Install it first:

Then set up the development environment:

```bash
uv sync
```

This installs all project dependencies, including development tools.

## Tools & Workflow

### Testing with pytest

Run the test suite:

```bash
uv run pytest
```

Tests are configured in `pyproject.toml` with a minimum coverage threshold of
80%. An HTML coverage report is automatically generated after each test run.

#### View coverage report

Open the coverage report in your browser:

```bash
uv run coverage-view
```

This starts a local HTTP server and opens the HTML coverage report, allowing you
to review which lines are covered by tests.

### Code Quality Tasks

We provide automated tasks for code formatting, linting, and type checking.

#### Run all checks

Execute formatting, linting, and type checking in one command:

```bash
uv run check
```

This runs the following checks in sequence with clear output:

- **Formatting**: Using `ruff format`
- **Linting**: Using `ruff check --fix`
- **Type Checking**: Using `ty check`

#### Individual tools

If you need to run specific checks manually, the underlying tools are available
as dev dependencies:

**Format all code:**

```bash
uv run ruff format
```

**Lint and fix issues:**

```bash
uv run ruff check --fix
```

**Type-check the codebase:**

```bash
uv run ty check
```

## Task System

Tasks in this project are defined in [src/tasks.py](src/tasks.py) and registered
in `pyproject.toml` under `[project.scripts]`.

### How Tasks Work

Tasks are organized into classes with static methods. Each task:

1. **Defines commands** using the `CMD` dataclass:

   ```python
   CMD(name="Task Description", args=["tool", "subcommand"])
   ```

2. **Executes via `uv_run()`** which runs `uv run` with the given arguments and
   displays formatted output

3. **Registered in pyproject.toml** for easy invocation:

   ```toml
   [project.scripts]
   check = "tasks:Check.main"
   coverage-view = "tasks:Coverage.view"
   ```

### Defining New Tasks

To add a new task:

1. Create a class in [src/tasks.py](src/tasks.py):

   ```python
   class MyTask:
       @staticmethod
       def main() -> None:
           """Description of what the task does."""
           commands: list[CMD] = [
               CMD(name="Step 1", args=["tool", "action"]),
               CMD(name="Step 2", args=["another-tool", "action"]),
           ]
           for cmd in commands:
               uv_run(cmd)
   ```

2. Register in `pyproject.toml`:

   ```toml
   my-task = "tasks:MyTask.main"
   ```

3. Run it:

   ```bash
   uv run my-task
   ```

### Task Design Principles

- **Organize logically**: Group related commands in classes
- **Provide clear names**: Use descriptive `CMD` names for output visibility
- **Keep it simple**: Each task should have a single, clear purpose

## Before Submitting

Make sure your changes pass all checks:

```bash
uv run check
```

> [!IMPORTANT]
> This project follows
> [conventional commits](https://gist.github.com/qoomon/5dfcdf8eec66a051ecd85625518cfd13).

## Project Structure

```text
src/sentinel/       # Main package code
src/tasks/          # Runnable tasks
tests/              # Test files
pyproject.toml      # Project configuration
```

## Questions?

Feel free to open an issue if you have any questions or need clarification!
