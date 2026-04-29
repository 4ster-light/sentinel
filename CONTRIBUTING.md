# Contributing to Sentinel

Thank you for your interest in contributing! This document outlines the
development workflow and tools we use.

## Development Setup

**Nix** is the recommended way to develop _Sentinel_ because it provides a more
reproducible environment.

Set up the development environment with:

```bash
nix develop
```

From there, use the helper commands in `justfile` (to see all available commands
run `just help`):

```bash
just test
just lint
just fmt
just check
```

If you prefer not to use Nix, `uv` is still a valid development setup (but isn't
a reproducible way to document bugs since the system isn't encapsulated):

```bash
just sync
```

## Tools & Workflow

### Testing with pytest

Run the test suite:

```bash
just test
```

Tests are configured in `pyproject.toml` with a minimum coverage threshold of
80%. An HTML coverage report is automatically generated after each test run.

#### View coverage report

After running tests, view the coverage report in your browser:

```bash
just serve
```

Then open <http://localhost:8000> in your browser to view the HTML coverage
report.

### Code Quality Checks

We use three main tools for code quality. Run them together or individually:

**Format all code:**

```bash
just fmt
```

**Lint and type-check:**

```bash
just lint
```

**Run all checks together:**

```bash
just fmt lint
```

## Before Submitting

Make sure your changes pass all checks and tests:

```bash
just fmt lint test
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
