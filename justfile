help:
    @echo ""
    @echo "    shell      Enter the Nix dev shell (recommended)"
    @echo "    sync       Sync uv dependencies (non-Nix setup)"
    @echo "    build      Build the Nix package"
    @echo "    check     Run flake checks"
    @echo "    test       Run pytest"
    @echo "    lint       Run ruff check + ty check"
    @echo "    fmt        Format code with ruff"
    @echo "    clean      Remove .venv"
    @echo "    gc         Garbage-collect unreachable Nix store paths"
    @echo ""

shell:
    nix develop

sync:
    uv sync

build:
    nix build

check:
    nix flake check

test:
    uv run pytest

lint:
    uv run ruff check --fix
    uv run ty check

fmt:
    uv run ruff format

serve:
    python -m http.server 8000 --directory htmlcov

clean:
    rm -rf .venv

gc:
    nix store gc
