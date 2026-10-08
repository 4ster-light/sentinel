alias b := build
alias t := test-all
alias s := serve
alias c := check

# Enter the Nix dev shell (recommended)
shell:
    nix develop

# Build the Nix default package
build:
    nix build

# Run all checks
check: test-all lint fmt-check
    nix flake check

# Run pytest
test-all:
    uv run pytest

# Run focused pytest targets or expressions (for example: just test -k restart)
[positional-arguments]
test *ARGS:
    uv run pytest --no-cov "$@"

# Lint code with ruff and type check with ty
lint:
    uv run ruff check
    uv run ty check

# Format code with ruff
fmt:
    uv run ruff format

# Verify formatting without modifying files
fmt-check:
    uv run ruff format --check

# Serve the coverage report
serve:
    python -m http.server 8000 --directory htmlcov
