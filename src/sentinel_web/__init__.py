"""Web dashboard for Sentinel: HTTP server, monitoring page and process data."""

from .data import collect_dashboard_data
from .page import DASHBOARD_PAGE
from .server import DashboardServer, create_dashboard_server

__all__ = [
	"DASHBOARD_PAGE",
	"DashboardServer",
	"collect_dashboard_data",
	"create_dashboard_server",
]
