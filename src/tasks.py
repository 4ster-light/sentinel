from dataclasses import dataclass
from subprocess import run
from rich import print


@dataclass
class CMD:
	name: str
	args: list[str]


def uv_run(cmd: CMD) -> None:
	print(f"[cyan][bold][underline]{cmd.name}...[/]")
	run(["uv", "run", *cmd.args], check=True)
	print()


class Check:
	@staticmethod
	def main() -> None:
		"""Task to run code formatting, linting, and type checking."""
		commands: list[CMD] = [
			CMD(name="Formatting", args=["ruff", "format"]),
			CMD(name="Linting", args=["ruff", "check", "--fix"]),
			CMD(name="Type Checking", args=["ty", "check"]),
		]

		for cmd in commands:
			uv_run(cmd)


class Coverage:
	@staticmethod
	def view() -> None:
		"""Start a local server and open the coverage report in the browser."""

		from http.server import SimpleHTTPRequestHandler
		import socketserver
		import webbrowser
		from pathlib import Path

		coverage_dir = Path("htmlcov")

		if not coverage_dir.exists():
			print("❌ No coverage report found. Run 'uv run pytest' first.")
			return

		port = 8000

		class CoverageHandler(SimpleHTTPRequestHandler):
			def __init__(self, *args, **kwargs):
				super().__init__(*args, directory=str(coverage_dir), **kwargs)

		with socketserver.TCPServer(("", port), CoverageHandler) as httpd:
			url = f"http://localhost:{port}/index.html"
			print(f"📊 Serving coverage report at {url}")
			print("Press Ctrl+C to stop the server")
			webbrowser.open(url)
			httpd.serve_forever()
