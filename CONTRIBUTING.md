# Contributing to Sentinel

Thank you for your interest in contributing! This document outlines the
development workflow and tools we use.

## Development Setup

**Nix** is the recommended way to develop _Sentinel_ because it provides a
reproducible environment and is the main build tool of the project.

Set up the development environment with:

```bash
nix develop
```

From there, use the helper commands in `justfile` (to see all available commands
run `just help`), some examples are:

```bash
just test  # pytest
just lint  # ruff lint
just fmt   # ruff format
just check # nix flake check
```

> [!NOTE]
> If you prefer not to use Nix, standalone `uv` is still a valid development
> setup (but isn't a reproducible way to validate submits since the system isn't
> encapsulated, therefore it will be treated as pending of validation), run the
> following to set up a virtual environment and install dependencies:
>
> ```bash
> uv sync
> ```

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

This project follows a _TDD (Test-Driven Development)_ workflow. Tests are the
source of truth for code correctness and expected behaviour. Therefore for a
build to be considered valid, all tests must pass, and these must have a minimum
coverage threshold of 80% (this is hardcoded in the pytest flags found in
`pyproject.toml` so tests will fail otherwise, so will do builds since they
execute a check phase as well).

We use three main tools for code quality. Run them together or individually:

**Format all code:**

```bash
just fmt
```

**Lint and type-check:**

```bash
just lint
```

**Check tests and build:**

```bash
just check
```

**Run all checks together:**

```bash
just fmt lint check
```

## Before Submitting

Make sure your changes pass all checks and tests:

```bash
just fmt lint check
```

Any new features or bug fixes should be accompanied by tests. If you are adding
a new feature, please include tests that cover the new functionality. All
mentioned checks should pass before submitting.

> [!IMPORTANT]
> This project follows
> [conventional commits](https://gist.github.com/qoomon/5dfcdf8eec66a051ecd85625518cfd13).

## Project Structure

```text
src/                # Source code of the different packages
  sentinel_core/    # Core library
  sentinel_cli/     # CLI interface
tests/              # Test files
pyproject.toml      # Project configuration
nix.flake           # Nix flake configuration
```

## Questions?

Feel free to open an issue if you have any questions or need clarification! Even
if you are not sure if your contribution is appropriate, we welcome respectfull
discussions and feedback.
