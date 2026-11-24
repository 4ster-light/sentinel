# Sentinel

[![Release](https://img.shields.io/github/v/release/4ster-light/sentinel?sort=semver&label=release&color=2f6f4e&style=flat-square&logo=github)](https://github.com/4ster-light/sentinel/releases/latest)
[![PyPI](https://img.shields.io/pypi/v/sentinel-pm?label=pypi&style=flat-square&logo=pypi&logoColor=white)](https://pypi.org/project/sentinel-pm/)
[![Nix flake](https://img.shields.io/badge/Nix-flake-5277C3?logo=nixos&logoColor=white&style=flat-square)](flake.nix)
[![COPR](https://img.shields.io/badge/Fedora-COPR-3c6eb4?logo=fedora&logoColor=white&style=flat-square)](https://copr.fedorainfracloud.org/coprs/4ster-light/sentinel-pm)
[![Linux](https://img.shields.io/badge/platform-Linux-teal?style=flat-square&logo=linux&logoColor=white)](#installation)
[![macOS](https://img.shields.io/badge/platform-macOS-teal?style=flat-square&logo=apple&logoColor=white)](#installation)

[![CI](https://img.shields.io/github/actions/workflow/status/4ster-light/sentinel/ci.yml?label=CI&style=flat-square&logo=githubactions&logoColor=white)](https://github.com/4ster-light/sentinel/actions/workflows/ci.yml)
[![COPR build](https://img.shields.io/copr/build/4ster-light/sentinel-pm/sentinel-pm?label=COPR&style=flat-square&logo=fedora&logoColor=white)](https://copr.fedorainfracloud.org/coprs/4ster-light/sentinel-pm/builds/)
[![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-3776AB?logo=python&logoColor=white&style=flat-square)](https://www.python.org/downloads/)

[![Sponsor](https://img.shields.io/badge/Sponsor-GitHub%20Sponsors-EA4AAA?logo=githubsponsors&logoColor=white&style=flat-square)](https://github.com/sponsors/4ster-light)
[![License: GPLv3](https://img.shields.io/badge/license-GPLv3-red?style=flat-square&logo=gnu&logoColor=white)](LICENSE)

## Table of Contents

- [Features](#features)
- [Installation](#installation)
  - [Fedora (COPR)](#fedora-copr)
  - [Nix](#nix)
  - [PyPI](#pypi)
  - [From Source](#from-source)
- [Commands Overview](#commands-overview)
- [Process Management](#process-management)
  - [Starting a Process](#starting-a-process)
  - [Startup Script Generation](#startup-script-generation)
  - [SysV init.d Scripts](#sysv-initd-scripts)
  - [Windows Services](#windows-services)
  - [Listing Processes](#listing-processes)
  - [Process Status](#process-status)
  - [Stopping Processes](#stopping-processes)
  - [Restarting Processes](#restarting-processes)
  - [Viewing Logs](#viewing-logs)
  - [Bulk Operations](#bulk-operations)
  - [Cleaning Up](#cleaning-up)
- [Auto-Restart](#auto-restart)
  - [Lazy Restart (Default)](#lazy-restart-default)
  - [Daemon Mode (Continuous Monitoring)](#daemon-mode-continuous-monitoring)
- [Process Groups](#process-groups)
  - [Creating Groups](#creating-groups)
  - [Managing Group Membership](#managing-group-membership)
  - [Listing Groups](#listing-groups)
  - [Group Operations](#group-operations)
  - [Deleting Groups](#deleting-groups)
- [Process Clusters](#process-clusters)
  - [Automatic Scaling](#automatic-scaling)
- [Port Management](#port-management)
  - [Allocating Ports](#allocating-ports)
  - [Listing Ports](#listing-ports)
  - [Freeing Ports](#freeing-ports)
- [Metrics Export](#metrics-export)
  - [Exporting Metrics](#exporting-metrics)
  - [Prometheus](#prometheus)
  - [Quick Snapshot](#quick-snapshot)
- [Web Dashboard](#web-dashboard)
- [Remote Management](#remote-management)
  - [Registering Remote Hosts](#registering-remote-hosts)
  - [Listing Remote Hosts](#listing-remote-hosts)
  - [Running Commands on Remote Hosts](#running-commands-on-remote-hosts)
  - [Removing Remote Hosts](#removing-remote-hosts)
- [Configuration](#configuration)
- [Environment Variables](#environment-variables)
  - [Process Environment](#process-environment)
  - [Process User](#process-user)
  - [Group Environment](#group-environment)
- [Getting Help](#getting-help)
- [License](#license)
- [Sponsor](#sponsor)

## Features

A lightweight process orchestrator CLI:

- Start and manage background processes with automatic logging
- Real-time CPU, memory, and uptime monitoring
- Automatic restart on process crash or exit
- Process groups for organizing related processes
- Size-based log rotation for stdout/stderr logs
- Optional HTTP/TCP process health checks
- Run processes as specific system users
- Port allocation and management
- Metrics export in JSON and table formats
- Built-in web dashboard for monitoring managed processes
- Automatic cluster scaling on CPU and memory load
- Remote process management via SSH
- Persistent state across sessions

## Installation

| Your situation | Recommended | What you get |
| --- | --- | --- |
| Fedora 44, 45 or rawhide | [Fedora (COPR)](#fedora-copr) | Native package, updated by `dnf`, dependencies from the distribution |
| NixOS or Nix | [Nix](#nix) | Flake package and dev shell, no system Python needed |
| Linux or macOS with Python 3.14+ | [PyPI](#pypi) | Isolated tool install, upgrades with `uv tool upgrade sentinel-pm` |
| Tracking `main` | [From Source](#from-source) | Latest unreleased changes from the repository |

### Fedora (COPR)

```bash
sudo dnf copr enable 4ster-light/sentinel-pm
sudo dnf install sentinel-pm
```

### Nix

```bash
nix profile add github:4ster-light/sentinel
```

On NixOS add the flake to your system configuration.

### PyPI

```bash
uv tool install sentinel-pm
```

With pip instead:

```bash
pip install sentinel-pm
```

### From Source

```bash
uv tool install git+https://github.com/4ster-light/sentinel
```

With pip instead:

```bash
pip install git+https://github.com/4ster-light/sentinel
```

## Commands Overview

| Command               | Description                       |
| --------------------- | --------------------------------- |
| `sentinel run`        | Start a background process        |
| `sentinel list`       | List all managed processes        |
| `sentinel status`     | Show detailed status of a process |
| `sentinel stop`       | Stop a running process            |
| `sentinel restart`    | Restart a process                 |
| `sentinel logs`       | View process logs                 |
| `sentinel clean`      | Remove dead processes from state  |
| `sentinel stopall`    | Stop all managed processes        |
| `sentinel startall`   | Start all stopped processes       |
| `sentinel restartall` | Restart all managed processes     |
| `sentinel up`         | Start a stack from a config file  |
| `sentinel daemon`     | Manage the restart monitor daemon |
| `sentinel group`      | Manage process groups             |
| `sentinel cluster`    | Manage process clusters           |
| `sentinel port`       | Manage port allocations           |
| `sentinel startup`    | Generate startup scripts          |
| `sentinel metrics`    | Export process metrics            |
| `sentinel dashboard`  | Serve a web monitoring dashboard  |
| `sentinel remote`     | Manage remote hosts via SSH       |

Run `sentinel run --help` to see process runtime options including `--user`,
`--startup-timeout`, `--instances`, `--scale`, `--autoscale`, `--depends-on`,
`--nice`, `--ionice`, and `--docker-image`.

## Process Management

### Starting a Process

Start a background process with `sentinel run`:

```bash
# Basic usage
sentinel run "python server.py"

# Give the process a name for easier reference
sentinel run "python server.py" --name myserver

# Start multiple instances with derived names
sentinel run "python server.py" --name web --instances 3

# Start a cluster that can grow later within a range
sentinel run "python server.py" --name web --scale 2-4

# Start only after another process is already running
sentinel run "python worker.py" --name worker --depends-on redis

# Enable auto-restart on crash or exit
sentinel run "npm start" --name frontend --restart

# Add process to a group
sentinel run "python worker.py" --name worker1 --group workers

# Use environment variables from a file
sentinel run "node app.js" --name app --env-file .env

# Run as a specific system user (name or uid)
sentinel run "python worker.py" --name worker --user deploy

# Add an HTTP health check (auto-restart still requires --restart)
sentinel run "python api.py" --name api --restart --health-http http://127.0.0.1:8000/health

# Add a TCP health check with custom thresholds
sentinel run "python worker.py" --name worker --restart --health-tcp 127.0.0.1:9000 --health-interval 10 --health-failures 2
```

`--depends-on` is repeatable and records the dependency on the process so
`group start`, `stopall`, `startall`, and `restartall` order their work by it:
dependencies start first and stop last. Each dependency is confirmed running
before its dependents start. Starting a process whose dependency is unknown or
not running is refused, and dependency cycles are reported before anything is
started.

When you use `--restart` without the daemon running, you will see a warning:

```txt
Started myserver (id: 1, pid: 12345)
Warning: Restart flag set but daemon is not running. Restarts will only happen
when you run other sentinel commands.
  Run 'sentinel daemon start' for continuous monitoring.
```

### Docker Process Isolation

Run a process inside a container with `--docker-image`:

```bash
# Nginx in a container with a published port
sentinel run "nginx -g 'daemon off;'" --name web --restart --docker-image nginx:alpine --docker-ports 8080:80

# Postgres with a bound volume, explicitly on podman
sentinel run "postgres" --name db --docker-image postgres:17 --docker-volumes pgdata:/var/lib/postgresql/data --docker-engine podman
```

How it works:

- The command is wrapped in an `<engine> run --rm` line and stored as the
  process command, so the whole lifecycle keeps working. Restarts respawn the
  container, logs land in the standard sentinel log files, health checks watch
  the published ports, and cluster instances get one container each, named
  `sentinel-<name>-<index>`.
- Without `--name`, the process name defaults to the image's short name.
- The engine is picked automatically: `docker` first, then `podman`.
  `--docker-engine` overrides the choice, and the resolved engine is recorded
  with the process so `stop` uses the same binary.
- `stop` runs `<engine> stop -t 10 <container>` and waits for the container to
  exit. The signal path stays the fallback.
- A single command is prefixed with `exec`, so it becomes PID 1 and receives
  the stop signal directly. A compound command keeps the shell as PID 1.
- Metrics report the wrapper process, not the container's own usage.
- `--docker-image` cannot be combined with `--user`, `--nice`, `--ionice` or
  `--cwd`. Those settings do not reach the container.
- Images must contain a shell, because the command runs through `sh -c`.

### Configuration File

`sentinel up` starts every process from one configuration file. It looks
for `sentinel.toml`, then `sentinel.yaml`, then `sentinel.yml` in the
current directory. Pass `--config FILE` to name a file directly.

Every process lives under `[processes.<name>]` in TOML or under
`processes.<name>` in YAML. The keys mirror the `run` flags: `restart`,
`user`, `group`, `env_file`, `cwd`, `health_http`, `health_tcp`,
`health_interval`, `health_timeout`, `health_failures`, `startup_timeout`,
`instances`, `scale`, `autoscale`, `depends_on`, `nice`, `ionice`, and a
`docker` table. `cmd` is required. A `name` key is rejected because the
table key already names the process.

TOML example:

```toml
[processes.db]
cmd = "postgres -D /srv/db"
restart = true

[processes.web]
cmd = "python app.py"
env_file = ".env"
cwd = "/srv/app"
health_http = "http://localhost:8000/health"
depends_on = ["db"]
group = "api"

[processes.box]
cmd = "nginx -g 'daemon off;'"
docker = { image = "nginx:alpine", ports = ["8080:80"] }
```

YAML example:

```yaml
processes:
  db:
    cmd: postgres -D /srv/db
    restart: true
  web:
    cmd: python app.py
    env_file: .env
    cwd: /srv/app
    health_http: http://localhost:8000/health
    depends_on:
      - db
    group: api
  box:
    cmd: nginx -g 'daemon off;'
    docker:
      image: nginx:alpine
      ports:
        - 8080:80
```

The `docker` table accepts `image`, `ports`, `volumes` and `engine`. The
rules match the `run` flags: `image` is required, `user`, `nice`, `ionice`
and `cwd` cannot be combined with a container, and the engine is picked
automatically unless `engine` names one.

`up` validates the whole file before it starts anything. Errors name the
file, the process and the key.

The per-process rules:

- A process that is not recorded is registered and started.
- A process that already runs with the same command is left alone and
  reported as already running.
- A recorded process that stopped starts again with its recorded settings.
- A recorded process with a different command is skipped with a warning
  that names the recorded command.
- Groups named in the file are created when they do not exist.
- `scale` and `instances` start numbered instances. `scale` starts the
  range minimum.
- `depends_on` orders the start. A dependency may name another file
  process or a recorded process. A cluster cannot be a dependency, because
  the batch starts whole instances.

The command prints created groups, started processes, processes that
already run, and conflicting definitions. It exits non-zero when a start
fails or a file process is not running at the end.

### Startup Script Generation

Generate a minimal systemd unit for a Sentinel-managed command:

```bash
sentinel startup systemd --name web --cwd /srv/web --restart python app.py
```

Output:

```ini
[Unit]
Description=Sentinel process: web
After=network.target

[Service]
Type=simple
WorkingDirectory=/srv/web
ExecStart=/usr/bin/env python app.py
Restart=always

[Install]
WantedBy=multi-user.target
```

### SysV init.d Scripts

Generate an LSB-compatible init script for systems that boot with SysV init or OpenRC's sysv-rc compatibility layer:

```bash
sentinel startup initd --name web --cwd /srv/web --user deploy -- python app.py
```

The script writes its PID to `/run/web.pid`, appends output to `/var/log/web.log`, and supports `start`, `stop`, `restart`, and `status`:

```bash
sudo sentinel startup initd --name web python app.py > /etc/init.d/web
sudo chmod +x /etc/init.d/web
sudo update-rc.d web defaults   # Debian and Ubuntu
sudo chkconfig --add web        # RHEL and Fedora
```

Use `--pidfile` and `--logfile` to override the default paths. The command runs in its own session, so `stop` signals the whole process group and escalates to `SIGKILL` if the process does not exit within 30 seconds.

### Windows Services

Generate a PowerShell script that installs the command as a Windows service through [NSSM](https://nssm.cc):

```powershell
sentinel startup windows --name web --cwd C:\srv\web --restart python app.py | Out-File install-web.ps1
```

Run the generated script from an elevated PowerShell prompt:

```powershell
.\install-web.ps1
.\install-web.ps1 -Uninstall   # remove the service again
```

The script registers `sentinel-web` with the automatic startup type and starts it. The first command token is the executable and the remaining tokens are its arguments. With `--restart` NSSM restarts the process when it exits; with `--user` the script prompts for the account password through `Get-Credential` instead of embedding a secret.

### Listing Processes

View all managed processes:

```bash
sentinel list
```

Output shows a table with ID, name, PID, status, CPU usage, memory usage,
uptime, restart flag, group, and command:

```txt
+----+----------+-------+---------+------+-------+--------+---------+---------+-------+-----------+
| ID | NAME     |   PID | STATUS  |  CPU |   MEM | UPTIME | RESTART | USER    | GROUP | COMMAND   |
+----+----------+-------+---------+------+-------+--------+---------+---------+-------+-----------+
|  1 | myserver | 12345 | running | 2.1% | 45 MB |   5m 3s|    -    |    -    |   -   | python ...|
|  2 | frontend | 12346 | running | 0.5% | 120MB |   2m 1s|    X    | deploy  |   -   | npm start |
+----+----------+-------+---------+------+-------+--------+---------+---------+-------+-----------+
```

### Process Status

Get detailed information about a specific process:

```bash
# By name
sentinel status myserver

# By ID
sentinel status 1
```

Output:

```txt
myserver (id: 1)
  PID:       12345
  Status:    running
  CPU:       2.1%
  Memory:    45.2MB
  Uptime:    5m 32s
  Restart:   no
  User:      default
  Group:     none
  CWD:       /home/user/project
  Command:   python server.py
  Stdout:    /home/user/.sentinel/logs/myserver.stdout.log
  Stderr:    /home/user/.sentinel/logs/myserver.stderr.log
```

### Stopping Processes

Stop a running process:

```bash
# By name
sentinel stop myserver

# By ID
sentinel stop 1

# Force kill (SIGKILL instead of SIGTERM)
sentinel stop myserver --force
```

Stopping signals the process's whole process group, so children of compound
commands (`npm run build && node server.js`, background jobs) die with the
leader.

### Restarting Processes

Restart a process (stops and starts it again):

```bash
sentinel restart myserver
```

### Viewing Logs

View stdout and stderr logs for a process:

```bash
# Show last 50 lines (default)
sentinel logs myserver

# Show last 100 lines
sentinel logs myserver --lines 100

# Follow log output in real-time
sentinel logs myserver --follow

# Show only stdout
sentinel logs myserver --stream stdout

# Show only stderr
sentinel logs myserver --stream stderr

# Clear logs
sentinel logs myserver --clear
```

Sentinel rotates process logs automatically when they exceed 10MB, keeping up to
3 backup files per stream (`.1`, `.2`, `.3`).

### Bulk Operations

Control all processes at once:

```bash
# Stop all processes
sentinel stopall

# Force stop all processes
sentinel stopall --force

# Start all stopped processes
sentinel startall

# Restart all processes
sentinel restartall
```

### Cleaning Up

Remove dead processes from the state file:

```bash
sentinel clean
```

This removes processes whose PIDs no longer exist from the state, without
affecting running processes.

## Auto-Restart

Sentinel can automatically restart processes that crash or exit. There are two
ways this works:

### Lazy Restart (Default)

When you run certain CLI commands (`list`, `status`), Sentinel checks for dead
processes and restarts those with the restart flag enabled. This happens
automatically without any extra setup.

Example:

```bash
# Start a process with restart flag
sentinel run "python worker.py" --name worker --restart

# If the process crashes, the next time you run list, it will be restarted
sentinel list
# Output: Auto-restarted worker (old_pid: 12345, new_pid: 12350)
```

### Daemon Mode (Continuous Monitoring)

For continuous monitoring without needing to run CLI commands, start the daemon:

```bash
# Start the daemon
sentinel daemon start
# Output: Started daemon (pid: 54321)

# Check daemon status
sentinel daemon status
# Output: Daemon is running (pid: 54321)

# Stop the daemon
sentinel daemon stop
# Output: Stopped daemon (pid: 54321)
```

When the daemon is running, it checks every 5 seconds for crashed processes,
restarts them automatically in the background, and resizes clusters that carry
an autoscaling policy. The daemon writes its activity to
`~/.sentinel/daemon.log` (rotated automatically).

## Process Groups

Groups let you organize related processes together.

### Creating Groups

```bash
# Create a group
sentinel group create workers

# Create a group with environment variables
sentinel group create production --env "NODE_ENV=production" --env "PORT=3000"
```

### Managing Group Membership

```bash
# Add a process to a group (by process ID)
sentinel group add workers 1

# Remove a process from a group
sentinel group remove workers 1
```

### Listing Groups

```bash
# List all groups
sentinel group list

# List processes in a specific group
sentinel group list workers
```

### Group Operations

Control all processes in a group:

```bash
# Start all processes in a group
sentinel group start workers

# Stop all processes in a group
sentinel group stop workers

# Restart all processes in a group
sentinel group restart workers
```

Group operations honor `--depends-on` ordering: `start` and `restart` start
dependencies first, while `stop` stops dependents first. A cycle or a missing
dependency aborts the start with a message naming the processes involved.

```bash
# Inspect the recorded dependencies of a process
sentinel status worker
```

### Deleting Groups

```bash
# Delete a group (processes are unassigned but not stopped)
sentinel group delete workers

# Delete a group and stop all its processes
sentinel group delete workers --with-processes

# Alias for --with-processes
sentinel group delete workers --stop
```

## Process Clusters

`--scale N` starts N instances with a fixed size. `--scale MIN-MAX` starts
`MIN` instances and records the range so the cluster can be resized later:

```bash
# Start two instances of web, growable up to four
sentinel run "python server.py" --name web --scale 2-4

# Show clusters, how many instances are running and their allowed range
sentinel cluster list

# Grow to four instances
sentinel cluster scale web 4

# Shrink back to two (the highest instance numbers are stopped)
sentinel cluster scale web 2
```

Scaling outside the recorded range is refused. Scaled-down instances are stopped
and removed from state, and a restart keeps an instance in its cluster.

### Automatic Scaling

A cluster with a range can also resize itself from load. Each metric is
`METRIC:HIGH:LOW`, and every metric is optional:

```bash
# Scale up when average CPU passes 80%, down below 40%
sentinel run "python worker.py" --name web --scale 2-4 --autoscale cpu:80:40

# Watch memory too (thresholds in megabytes)
sentinel run "python worker.py" --name web --scale 2-4 --autoscale cpu:80:40 --autoscale mem:800:300

# Scale on a number the process writes to a file
sentinel run "python worker.py" --name web --scale 2-4 --autoscale metric:/run/app/depth:80:40

# Set or remove the policy on an existing cluster
sentinel cluster autoscale web --cpu 80:40 --mem 800:300
sentinel cluster autoscale web --metric /run/app/depth:80:40 --cooldown 15 --step 2
sentinel cluster autoscale web --clear
```

The cluster grows while any configured metric crosses HIGH, and shrinks only
when every configured metric falls below LOW. A custom metric names a file the
process updates with its current value. A missing, unreadable, unparsable or
stale file causes no action. A file older than 60 seconds counts as stale.
Each policy carries its own cooldown and step. The defaults keep a 30 second
cooldown and one instance per adjustment. The run flags `--autoscale-cooldown`
and `--autoscale-step` and the `cluster autoscale` flags `--cooldown` and
`--step` tune them. The daemon evaluates the policy on its 5-second scan, so
run `sentinel daemon start` for automatic adjustments. `cluster list` shows
the policy of each cluster.

## Port Management

Sentinel can allocate and track ports for your processes.

### Allocating Ports

```bash
# Allocate a random available port
sentinel port allocate
# Output: Allocated port 8234 (default)

# Allocate a specific port
sentinel port allocate --port 8000

# Allocate with a name
sentinel port allocate --name myapp
# Output: Allocated port 9123 (myapp)
```

### Listing Ports

```bash
sentinel port list
```

Output:

```txt
+-------+---------+------------------+
|  PORT | NAME    | ALLOCATED        |
+-------+---------+------------------+
|  8000 | myapp   | 2024-01-15 10:30 |
|  8234 | default | 2024-01-15 10:35 |
+-------+---------+------------------+
```

### Freeing Ports

```bash
sentinel port free 8000
```

## Metrics Export

Export process metrics in different formats for monitoring and automation.

### Exporting Metrics

```bash
# Show metrics as a table (default)
sentinel metrics export

# Export as JSON
sentinel metrics export --format json

# Write metrics to a file
sentinel metrics export --output metrics.json

# Export JSON to a file
sentinel metrics export --format json --output metrics.json
```

Output (table format):

```txt
+----+----------+-------+---------+------+-------+--------+
| ID | NAME     |   PID | STATUS  |  CPU |   MEM | UPTIME |
+----+----------+-------+---------+------+-------+--------+
|  1 | myserver | 12345 | running | 2.1% | 45 MB |   5m 3s|
|  2 | frontend | 12346 | running | 0.5% | 120MB |   2m 1s|
+----+----------+-------+---------+------+-------+--------+
```

Output (JSON format):

```json
[
  {
    "id": 1,
    "name": "myserver",
    "pid": 12345,
    "status": "running",
    "running": true,
    "cpu_percent": 2.1,
    "memory_mb": 45.2,
    "uptime_seconds": 303.0
  }
]
```

### Prometheus

Export the metrics in the Prometheus text exposition format, or let Prometheus scrape them from a built-in HTTP endpoint:

```bash
# Write the exposition format to stdout
sentinel metrics export --format prometheus

# Write it to a file for the node exporter textfile collector
sentinel metrics export --format prometheus --output /var/lib/node_exporter/sentinel.prom

# Serve http://127.0.0.1:9464/metrics for Prometheus to scrape
sentinel metrics serve
```

Example output:

```txt
# HELP sentinel_processes_total Number of processes tracked by Sentinel.
# TYPE sentinel_processes_total gauge
sentinel_processes_total 2
# HELP sentinel_process_up Whether Sentinel sees the process as running (1) or not (0).
# TYPE sentinel_process_up gauge
sentinel_process_up{id="1",name="myserver"} 1
sentinel_process_up{id="2",name="frontend"} 0
# HELP sentinel_process_cpu_percent CPU usage of the process, in percent.
# TYPE sentinel_process_cpu_percent gauge
sentinel_process_cpu_percent{id="1",name="myserver"} 2.1
```

Add the scrape target to `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: sentinel
    static_configs:
      - targets: ["127.0.0.1:9464"]
```

The endpoint renders metrics on every scrape, so values are always current, and answers `404` for any path other than `/metrics`.

### Quick Snapshot

Print a one-shot metrics table to stdout:

```bash
sentinel metrics snapshot
```

This is equivalent to `sentinel metrics export` without options.

## Web Dashboard

Sentinel serves a self-contained live page with no external assets:

```bash
# Serve at http://127.0.0.1:7331/
sentinel dashboard

# Choose the address and port
sentinel dashboard --host 0.0.0.0 --port 8080
```

The page lists every managed process with its status, CPU, memory, uptime,
group, and cluster. It updates itself through a Server-Sent Events stream:
the server samples the process state once per tick and feeds every open tab
from one pass, and the page reconnects by itself after a drop. The same
data is available as JSON for scripting:

```bash
curl http://127.0.0.1:7331/api/processes
```

`Ctrl+C` stops the server. With `sentinel daemon start` running, crashed
processes restart in the background while you watch.

### Control actions

Each row carries buttons: `Stop`, `Restart`, and `Start` act on the process,
and `Scale up` and `Scale down` change its cluster size. Each action calls
the same core functions as the CLI. The page reports the outcome in a
status line.

### Control token

On the default loopback bind the actions work without extra setup. Binding
beyond loopback requires a control token, and the server refuses to start
without one:

```bash
sentinel dashboard --host 0.0.0.0 --control-token <secret>
```

Control requests must carry the token in the `X-Control-Token` header. The
page asks for the token when an action is refused and sends it with every
later action:

```bash
curl -X POST -H "X-Control-Token: <secret>" http://<host>:7331/api/processes/1/stop
```

## Remote Management

Manage processes on remote hosts via SSH. Remote hosts must have Sentinel
installed and accessible via SSH.

### Registering Remote Hosts

```bash
# Add a remote host
sentinel remote add server1.example.com

# Add with SSH user
sentinel remote add server1.example.com --user deploy

# Add with custom SSH port
sentinel remote add server1.example.com --user deploy --port 2222
```

### Listing Remote Hosts

```bash
# List all registered remote hosts
sentinel remote list
```

Output:

```txt
+---------------------+--------+------+------------------+
| HOST                | USER   | PORT | CREATED          |
+---------------------+--------+------+------------------+
| server1.example.com | deploy | 2222 | 2024-01-15 10:30 |
| server2.example.com | -      | -    | 2024-01-15 10:35 |
+---------------------+--------+------+------------------+
```

### Running Commands on Remote Hosts

```bash
# List processes on a remote host
sentinel remote list server1.example.com

# Start a process on a remote host
sentinel remote run server1.example.com "python server.py"

# Stop a process on a remote host (use the ID shown by `remote list`)
sentinel remote stop server1.example.com 1
```

### Removing Remote Hosts

```bash
sentinel remote remove server1.example.com
```

## Configuration

Sentinel stores its state in `~/.sentinel/` by default (override the directory
with the `SENTINEL_STATE_DIR` environment variable):

- `state.json` - Process registry, port allocations, and remote hosts.
  Written atomically and guarded against corruption.
- `state.json.lock` - Advisory lock coordinating concurrent Sentinel
  writers (the daemon and CLI commands).
- `logs/` - Process stdout and stderr logs
- `daemon.pid` - PID file for the restart daemon
- `daemon.log` - Rotating log of daemon activity (restarts, errors)

If `state.json` is ever unreadable, Sentinel backs it up to
`state.json.corrupt-<timestamp>`, prints a warning, and starts from an empty
state instead of silently discarding your data.

## Environment Variables

### Process Environment

You can pass environment variables to processes:

```bash
# Using an env file
sentinel run "node app.js" --env-file .env
```

Sentinel also looks for environment files in:

- `~/.sentinel/.env` (global)
- `./.env` (current directory)

### Process User

Run commands as a specific local system user:

```bash
# Run by username
sentinel run "python worker.py" --name worker --user deploy

# Run by uid
sentinel run "python worker.py" --name worker --user 1001
```

Notes:

- Switching to another user generally requires root privileges.
- If you run Sentinel without root, use your current user.

### Group Environment

Groups can have environment variables that are passed to all processes in the
group:

```bash
sentinel group create staging --env "DATABASE_URL=postgres://..." --env "DEBUG=true"
```

## Getting Help

View available commands:

```bash
sentinel --help
```

Get help for a specific command:

```bash
sentinel run --help
sentinel daemon --help
sentinel group --help
sentinel port --help
sentinel metrics --help
sentinel remote --help
```

## License

[![License: GPLv3](https://img.shields.io/badge/license-GPLv3-red?style=flat-square&logo=gnu&logoColor=white)](LICENSE)

## Sponsor

Consider sponsoring if you like this proyect:

[![Sponsor](https://img.shields.io/badge/Sponsor-GitHub%20Sponsors-EA4AAA?logo=githubsponsors&logoColor=white&style=flat-square)](https://github.com/sponsors/4ster-light)
