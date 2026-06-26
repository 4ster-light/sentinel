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

        appDescription = "A lightweight process orchestrator CLI";

        sentinel = py.buildPythonApplication {
          pname = "sentinel";
          version = "0.2.1+fix";
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
            description = appDescription;
            homepage = "https://sentinel.4ster.deno.net";
            license = licenses.mit;
            mainProgram = "sentinel";
          };
        };

        containerImage = pkgs.dockerTools.buildLayeredImage {
          name = "sentinel";
          tag = "latest";
          contents = [ sentinel ];
          config = {
            Entrypoint = [ "${sentinel}/bin/sentinel" ];
          };
        };

      in
      {
        packages = {
          default = sentinel;
          sentinel = sentinel;
          container = containerImage;
        };

        apps.default = {
          type = "app";
          program = "${sentinel}/bin/sentinel";
          meta.description = appDescription;
        };

        checks = {
          package = sentinel;

          smoke =
            pkgs.runCommand "sentinel-smoke-test"
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
            echo "Sentinel Nix dev shell — $(python --version)"
            echo ""
            echo "See all commands:  just help"
            echo ""
          '';
        };
      }
    );
}
