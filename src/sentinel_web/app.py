"""FastAPI application serving the monitoring dashboard."""

from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from sentinel_core.state import State

from .data import collect_dashboard_data

_PACKAGE_DIR = Path(__file__).resolve().parent

templates = Jinja2Templates(directory=str(_PACKAGE_DIR / "templates"))


class ProcessRow(BaseModel):
	id: int
	name: str
	pid: int
	status: str
	running: bool
	cpu_percent: float
	memory_mb: float
	uptime_seconds: float
	group: str | None
	cluster: str | None
	cluster_index: int | None


class DashboardSnapshot(BaseModel):
	processes: list[ProcessRow]
	updated_at: str


def create_dashboard_app(state_loader: Callable[[], State]) -> FastAPI:
	"""Build the read-only dashboard app: the page at / and data at /api/processes."""
	app = FastAPI(title="Sentinel dashboard", docs_url=None, redoc_url=None, openapi_url=None)
	app.mount("/static", StaticFiles(directory=str(_PACKAGE_DIR / "static")), name="static")

	@app.get("/")
	def dashboard(request: Request) -> HTMLResponse:
		return templates.TemplateResponse(request, "dashboard.html")

	@app.get("/api/processes", response_model=DashboardSnapshot)
	def processes() -> DashboardSnapshot:
		return DashboardSnapshot.model_validate(collect_dashboard_data(state_loader()))

	return app
