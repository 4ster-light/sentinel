"""Dashboard data: process metrics plus group and cluster labels."""

from datetime import datetime
from typing import Any

from sentinel_core.metrics import collect_metrics
from sentinel_core.state import State


def collect_dashboard_data(state: State) -> dict[str, Any]:
	"""One dashboard refresh: process metrics plus group and cluster labels."""
	infos = {info.id: info for info in state.list_processes()}
	rows: list[dict[str, Any]] = []
	for metric in collect_metrics(state):
		info = infos.get(metric.id)
		rows.append(
			{
				**metric.to_dict(),
				"group": info.group if info else None,
				"cluster": info.cluster if info else None,
				"cluster_index": info.cluster_index if info else None,
			}
		)
	return {"processes": rows, "updated_at": datetime.now().isoformat(timespec="seconds")}
