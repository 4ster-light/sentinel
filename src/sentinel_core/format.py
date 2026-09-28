"""Human-readable formatting helpers"""

from datetime import datetime


def uptime_from_started_at(started_at: str) -> float:
	"""Seconds since the given ISO timestamp, or 0 if it cannot be parsed."""
	try:
		start = datetime.fromisoformat(started_at)
		return (datetime.now() - start).total_seconds()
	except ValueError:
		return 0.0


def format_uptime_seconds(seconds: float) -> str:
	secs = int(seconds)
	if secs < 60:
		return f"{secs}s"
	if secs < 3600:
		return f"{secs // 60}m {secs % 60}s"
	if secs < 86400:
		return f"{secs // 3600}h {(secs % 3600) // 60}m"
	return f"{secs // 86400}d {(secs % 86400) // 3600}h"


def format_memory_mb(mb: float) -> str:
	if mb < 1:
		return f"{mb * 1024:.0f}KB"
	if mb < 1024:
		return f"{mb:.1f}MB"
	return f"{mb / 1024:.2f}GB"
