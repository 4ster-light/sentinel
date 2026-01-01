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

### Code formatting and checking

The tasks module provides a unified script for formatting, linting, and type
checking that can be run as follows:

```bash
uv run check
```

But in case of wanting any specific step `ruff` and `ty`, which are the used
tools, are available as dev dependencies and can be used individually:

#### Ruff

Format all code:

```bash
uv run ruff format
```

Lint and fix any fizable errors:

```bash
uv run ruff check --fix
```

#### Type checking with ty

Type-check the codebase:

```bash
uv run ty check
```

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
