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

After running tests, view the coverage report in your browser:

```bash
python -m http.server 8000 --directory htmlcov
```

Then open <http://localhost:8000> in your browser to view the HTML coverage
report.

### Code Quality Checks

We use three main tools for code quality. Run them together or individually:

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

**Run all checks together:**

```bash
uv run ruff format && uv run ruff check --fix && uv run ty check
```

## Before Submitting

Make sure your changes pass all checks and tests:

```bash
# Run tests
uv run pytest

# Format, lint, and type check
uv run ruff format && uv run ruff check --fix && uv run ty check
```

> [!IMPORTANT]
> This project follows
> [conventional commits](https://gist.github.com/qoomon/5dfcdf8eec66a051ecd85625518cfd13).

## Project Structure

```text
src/sentinel/       # Main package code
tests/              # Test files
pyproject.toml      # Project configuration
```

## Questions?

Feel free to open an issue if you have any questions or need clarification!
