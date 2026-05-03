{
  description = "sentinel – process supervisor cli";

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

        sentinel = py.buildPythonApplication {
          pname = "sentinel";
          version = "0.1.5";
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

          pythonImportsCheck = [
            "sentinel_core"
            "sentinel_cli"
          ];

          doCheck = false;

          meta = with lib; {
            description = "A simple process supervisor CLI";
            homepage = "https://github.com/4ster-light/sentinel";
            license = licenses.mit;
            mainProgram = "sentinel";
          };
        };

      in
      {
        packages = {
          default = sentinel;
          sentinel = sentinel;
        };

        apps.default = flake-utils.lib.mkApp {
          drv = sentinel;
        };

        checks = {
          package = sentinel;

          smoke =
            pkgs.runCommand "sentinel-smoke-test"
              {
                buildInputs = [ sentinel ];
              }
              ''
                sentinel --help > "$out"
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
          ];

          UV_PROJECT_ENVIRONMENT = ".venv";

          shellHook = ''
            if [ ! -d .venv ]; then
              echo "→ Creating project venv..."
              uv venv
            fi

            echo ""
            echo "Sentinel Nix dev shell — $(python --version)"
            echo ""
            echo "See all commands:  just help"
            echo "Setup:             just sync"
            echo ""
          '';
        };
      }
    );
}
