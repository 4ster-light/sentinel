"""View HTML coverage report."""

import http.server
import socketserver
import webbrowser
from pathlib import Path


def main() -> None:
	"""Start a local server and open the coverage report in the browser."""
	coverage_dir = Path("htmlcov")

	if not coverage_dir.exists():
		print("❌ No coverage report found. Run 'uv run pytest' first.")
		return

	port = 8000
	handler = http.server.SimpleHTTPRequestHandler

	class CoverageHandler(handler):
		def __init__(self, *args, **kwargs):
			super().__init__(*args, directory=str(coverage_dir), **kwargs)

	with socketserver.TCPServer(("", port), CoverageHandler) as httpd:
		url = f"http://localhost:{port}/index.html"
		print(f"📊 Serving coverage report at {url}")
		print("Press Ctrl+C to stop the server")
		webbrowser.open(url)
		httpd.serve_forever()
