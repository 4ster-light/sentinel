{
  description = "Sentinel - Lightweight process orchestrator cli";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs { inherit system; };
        lib = pkgs.lib;
        python = pkgs.python314;
        py = python.pkgs;

        pyproject = builtins.readFile ./pyproject.toml |> fromTOML;

        sentinel = py.buildPythonApplication {
          pname = pyproject.project.name;
          version = pyproject.project.version;
          format = "pyproject";
          src = ./.;

          nativeBuildInputs = [
            py.hatchling
          ];

          propagatedBuildInputs = [
            py.psutil
            py.rich
            py.typer
          ];

          nativeCheckInputs = [
            py.pytestCheckHook
            py.pytest-cov
          ];

          pythonImportsCheck = [
            "sentinel_core"
            "sentinel_cli"
          ];

          doCheck = true;

          preCheck = ''
            export HOME=$(mktemp -d)
            export TMPDIR=$(mktemp -d)
          '';

          meta = with lib; {
            description = pyproject.project.description;
            homepage = pyproject.project.urls.Homepage;
            license = licenses.mit;
            mainProgram = pyproject.project.name;
          };
        };
      in
      {
        packages = {
          default = sentinel;
          sentinel = sentinel;
        };

        apps.default = {
          type = "app";
          program = "${sentinel}/bin/${pyproject.project.name}";
          meta.description = pyproject.project.description;
        };

        checks = {
          package = sentinel;

          smoke =
            pkgs.runCommand "${pyproject.project.name}-smoke-test"
              {
                buildInputs = [ sentinel ];
              }
              ''
                mkdir -p "$out"
                sentinel --help > "$out/help.txt"
                sentinel run --help > "$out/run-help.txt"
              '';
        };

        devShells.default = pkgs.mkShell {
          packages = [
            python
            pkgs.uv
            pkgs.ruff
            pkgs.ty
            pkgs.just
            pkgs.git
            py.pytest
            py.pytest-cov
          ];

          UV_PROJECT_ENVIRONMENT = ".venv";

          shellHook = ''
            if [ ! -d .venv ]; then
              echo "→ Creating project venv..."
              uv venv
            fi

            echo ""
            echo "${pyproject.project.name} nix dev shell — $(python --version)"
            echo ""
            echo "See all available commands:  just -l"
            echo ""
          '';
        };
      }
    );
}
