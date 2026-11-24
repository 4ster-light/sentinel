const rows = document.getElementById("rows");
const updated = document.getElementById("updated");
const empty = document.getElementById("empty");
const status = document.getElementById("action-status");
const tokenRow = document.getElementById("token-row");
const token = document.getElementById("token");

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

function actionButton(label, action, target) {
	const button = document.createElement("button");
	button.className = "action";
	button.textContent = label;
	button.dataset.action = action;
	button.dataset.target = target;
	return button;
}

function actionsCell(process) {
	const td = document.createElement("td");
	const stop = actionButton("Stop", "stop", process.id);
	const restart = actionButton("Restart", "restart", process.id);
	const start = actionButton("Start", "start", process.id);
	stop.disabled = !process.running;
	restart.disabled = !process.running;
	start.disabled = process.running;
	td.append(stop, restart, start);
	if (process.cluster) {
		td.append(
			actionButton("Scale up", "scale-up", process.cluster),
			actionButton("Scale down", "scale-down", process.cluster),
		);
	}
	return td;
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
			actionsCell(process),
		);
		rows.append(row);
	}
	empty.hidden = data.processes.length > 0;
	updated.textContent = data.updated_at ? "Updated " + data.updated_at : "";
}

async function control(action, target) {
	const headers = {};
	if (token.value) headers["X-Control-Token"] = token.value;
	let url;
	let body;
	if (action === "scale-up" || action === "scale-down") {
		url = "/api/clusters/" + encodeURIComponent(target) + "/scale";
		body = JSON.stringify({ direction: action === "scale-up" ? "up" : "down" });
	} else {
		url = "/api/processes/" + encodeURIComponent(target) + "/" + action;
	}
	try {
		const response = await fetch(url, { method: "POST", headers, body });
		const payload = await response.json();
		if (response.status === 401) {
			tokenRow.hidden = false;
			token.focus();
			status.textContent = payload.detail;
			status.className = "status error";
			return;
		}
		status.textContent = response.ok ? payload.message : payload.detail;
		status.className = response.ok ? "status ok" : "status error";
	} catch {
		status.textContent = "Sentinel did not answer.";
		status.className = "status error";
	}
}

rows.addEventListener("click", (event) => {
	const button = event.target.closest("button.action");
	if (!button || !rows.contains(button)) return;
	control(button.dataset.action, button.dataset.target);
});

function connect() {
	const source = new EventSource("/events");
	source.onmessage = (event) => render(JSON.parse(event.data));
	source.onerror = () => {
		updated.textContent = "Waiting for Sentinel...";
	};
}

connect();
