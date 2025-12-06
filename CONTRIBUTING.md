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

Run with coverage:

```bash
uv run pytest --cov=sentinel
```

### Code formatting with ruff

Format all code:

```bash
uv run ruff format
```

Check formatting without making changes:

```bash
uv run ruff check
```

### Type checking with ty

Type-check the codebase:

```bash
uv run ty check
```

## Before Submitting

Make sure your changes pass all checks:

1. **Format**: `uv run ruff format`
2. **Type check**: `uv run ty check`
3. **Tests**: `uv run pytest`

## Project Structure

```text
src/sentinel/       # Main package code
tests/              # Test files
pyproject.toml      # Project configuration
```

## Questions?

Feel free to open an issue if you have any questions or need clarification!
