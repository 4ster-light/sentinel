"""FastAPI application serving the live dashboard."""

import secrets
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from sentinel_core.cluster import cluster_members, scale_cluster
from sentinel_core.models import ProcessInfo
from sentinel_core.process import managed_process, restart_from_info, restart_process, stop_process
from sentinel_core.state import State

from .data import collect_dashboard_data
from .events import EventBroadcaster

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


class ActionOutcome(BaseModel):
	message: str


class ScaleRequest(BaseModel):
	direction: Literal["up", "down"]


def _find_process_or_404(state: State, process_id: int) -> ProcessInfo:
	info = state.find_process(process_id)
	if info is None:
		raise HTTPException(status_code=404, detail=f"Process not found: {process_id}")
	return info


def create_dashboard_app(
	state_loader: Callable[[], State],
	*,
	control_token: str | None = None,
	event_interval: float = 2.0,
) -> FastAPI:
	"""Build the live dashboard: the page, the event stream and control endpoints."""

	def sample() -> str:
		return DashboardSnapshot.model_validate(collect_dashboard_data(state_loader())).model_dump_json()

	broadcaster = EventBroadcaster(sample, interval=event_interval)

	@asynccontextmanager
	async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
		yield
		await broadcaster.close()

	def require_control(request: Request) -> None:
		# A loopback bind is trusted; a configured token gates every control action.
		if control_token is None:
			return
		presented = request.headers.get("x-control-token", "")
		if not presented or not secrets.compare_digest(presented.encode("utf-8"), control_token.encode("utf-8")):
			raise HTTPException(status_code=401, detail="Control requires a valid token")

	app = FastAPI(title="Sentinel dashboard", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
	app.mount("/static", StaticFiles(directory=str(_PACKAGE_DIR / "static")), name="static")
	control = [Depends(require_control)]

	@app.get("/")
	def dashboard(request: Request) -> HTMLResponse:
		return templates.TemplateResponse(request, "dashboard.html")

	@app.get("/api/processes", response_model=DashboardSnapshot)
	def processes() -> DashboardSnapshot:
		return DashboardSnapshot.model_validate(collect_dashboard_data(state_loader()))

	@app.get("/events")
	def events() -> StreamingResponse:
		return StreamingResponse(
			broadcaster.stream(),
			media_type="text/event-stream",
			headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
		)

	@app.post("/api/processes/{process_id}/stop", response_model=ActionOutcome, dependencies=control)
	def stop_control(process_id: int) -> ActionOutcome:
		state = state_loader()
		_find_process_or_404(state, process_id)
		try:
			stopped = stop_process(state, process_id)
		except ValueError as error:
			raise HTTPException(status_code=400, detail=str(error)) from error
		return ActionOutcome(message=f"Stopped {stopped.name}")

	@app.post("/api/processes/{process_id}/restart", response_model=ActionOutcome, dependencies=control)
	def restart_control(process_id: int) -> ActionOutcome:
		state = state_loader()
		_find_process_or_404(state, process_id)
		try:
			restarted = restart_process(state, process_id)
		except ValueError as error:
			raise HTTPException(status_code=400, detail=str(error)) from error
		return ActionOutcome(message=f"Restarted {restarted.name}")

	@app.post("/api/processes/{process_id}/start", response_model=ActionOutcome, dependencies=control)
	def start_control(process_id: int) -> ActionOutcome:
		state = state_loader()
		info = _find_process_or_404(state, process_id)
		if not info.stopped and managed_process(info) is not None:
			raise HTTPException(status_code=400, detail=f"Process '{info.name}' is already running")
		try:
			started = restart_from_info(state, info)
		except ValueError as error:
			raise HTTPException(status_code=400, detail=str(error)) from error
		return ActionOutcome(message=f"Started {started.name}")

	@app.post("/api/clusters/{cluster}/scale", response_model=ActionOutcome, dependencies=control)
	def scale_control(cluster: str, request: ScaleRequest) -> ActionOutcome:
		state = state_loader()
		members = cluster_members(state, cluster)
		if not members:
			raise HTTPException(status_code=404, detail=f"Unknown cluster '{cluster}'")
		desired = len(members) + (1 if request.direction == "up" else -1)
		try:
			scale_cluster(state, cluster, desired)
		except ValueError as error:
			raise HTTPException(status_code=400, detail=str(error)) from error
		return ActionOutcome(message=f"Scaled {cluster} to {desired} instances")

	return app
