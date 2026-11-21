"""The self-contained monitoring page served at the dashboard root."""

DASHBOARD_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sentinel dashboard</title>
<style>
	:root { color-scheme: light dark; }
	body { margin: 0; font: 14px/1.45 system-ui, sans-serif; }
	main { max-width: 1100px; margin: 0 auto; padding: 24px 16px 48px; }
	h1 { font-size: 18px; margin: 0; }
	.updated { color: gray; font-size: 12px; margin: 4px 0 16px; min-height: 1em; }
	table { width: 100%; border-collapse: collapse; }
	th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid rgba(128, 128, 128, 0.35); white-space: nowrap; }
	th { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; }
	tbody tr:hover { background: rgba(128, 128, 128, 0.12); }
	.num { text-align: right; font-variant-numeric: tabular-nums; }
	.running { color: #2e7d32; }
	.not-running { color: #c62828; }
	.empty { color: gray; }
</style>
</head>
<body>
<main>
	<h1>Sentinel</h1>
	<div class="updated" id="updated"></div>
	<table>
		<thead>
			<tr>
				<th class="num">ID</th><th>Name</th><th class="num">PID</th><th>Status</th>
				<th class="num">CPU</th><th class="num">Memory</th><th class="num">Uptime</th>
				<th>Group</th><th>Cluster</th>
			</tr>
		</thead>
		<tbody id="rows"></tbody>
	</table>
	<p class="empty" id="empty" hidden>No processes are being managed yet.</p>
</main>
<script>
const rows = document.getElementById("rows");
const updated = document.getElementById("updated");
const empty = document.getElementById("empty");

// Names come from user commands; only textContent is used, so they can never inject markup.
function cell(value, className) {
	const td = document.createElement("td");
	td.textContent = value;
	if (className) td.className = className;
	return td;
}

function formatUptime(seconds) {
	if (seconds < 60) return Math.round(seconds) + "s";
	const minutes = Math.floor(seconds / 60);
	if (minutes < 60) return minutes + "m " + Math.round(seconds % 60) + "s";
	return Math.floor(minutes / 60) + "h " + (minutes % 60) + "m";
}

function formatMemory(mb) {
	return mb >= 1024 ? (mb / 1024).toFixed(1) + " GiB" : mb.toFixed(1) + " MiB";
}

function render(data) {
	rows.replaceChildren();
	for (const process of data.processes) {
		const row = document.createElement("tr");
		row.append(
			cell(process.id, "num"),
			cell(process.name),
			cell(process.pid, "num"),
			cell(process.status, process.running ? "running" : "not-running"),
			cell(process.cpu_percent.toFixed(1) + "%", "num"),
			cell(formatMemory(process.memory_mb), "num"),
			cell(formatUptime(process.uptime_seconds), "num"),
			cell(process.group ?? ""),
			cell(process.cluster ?? ""),
		);
		rows.append(row);
	}
	empty.hidden = data.processes.length > 0;
	updated.textContent = data.updated_at ? "Updated " + data.updated_at : "";
}

async function refresh() {
	try {
		const response = await fetch("/api/processes");
		if (response.ok) render(await response.json());
	} catch {
		updated.textContent = "Waiting for Sentinel...";
	}
	setTimeout(refresh, 5000);
}

refresh();
</script>
</body>
</html>
"""
