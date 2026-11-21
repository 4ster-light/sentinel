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
