<div align="center">

# Sentinel

[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Sponsor](https://img.shields.io/badge/Sponsor-GitHub%20Sponsors-EA4AAA?logo=githubsponsors)](https://github.com/sponsors/4ster-light)

**A lightweight process orchestrator CLI**

</div>

<br />

## Features

- Start and manage background processes with automatic logging
- Real-time CPU, memory, and uptime monitoring
- Automatic restart on process crash or exit
- Process groups for organizing related processes
- Size-based log rotation for stdout/stderr logs
- Optional HTTP/TCP process health checks
- Run processes as specific system users
- Port allocation and management
- Metrics export in JSON and table formats
- Remote process management via SSH
- Persistent state across sessions

## Installation

For more installation options, see the
[installation guide in the docs](https://sentinel.4ster.deno.net/en/guide/installation).

### Nix

```bash
nix profile add github:4ster-light/sentinel
```

If you are on NixOS add the flake to your system configuration.

### Python [(Uv)](https://docs.astral.sh/uv)

```bash
uv tool install git+https://github.com/4ster-light/sentinel
```

Alternatively using pip:

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
| `sentinel daemon`     | Manage the restart monitor daemon |
| `sentinel group`      | Manage process groups             |
| `sentinel port`       | Manage port allocations           |
| `sentinel startup`    | Generate startup scripts          |
| `sentinel metrics`    | Export process metrics            |
| `sentinel remote`     | Manage remote hosts via SSH       |

Run `sentinel run --help` to see process runtime options including `--user`,
`--startup-timeout`, `--instances`, `--nice`, and `--ionice`.

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

When you use `--restart` without the daemon running, you will see a warning:

```txt
Started myserver (id: 1, pid: 12345)
Warning: Restart flag set but daemon is not running. Restarts will only happen
when you run other sentinel commands.
  Run 'sentinel daemon start' for continuous monitoring.
```

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

When the daemon is running, it checks every 5 seconds for crashed processes and
restarts them automatically in the background. The daemon writes its activity
to `~/.sentinel/daemon.log` (rotated automatically).

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

### Deleting Groups

```bash
# Delete a group (processes are unassigned but not stopped)
sentinel group delete workers

# Delete a group and stop all its processes
sentinel group delete workers --with-processes

# Alias for --with-processes
sentinel group delete workers --stop
```

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

### Quick Snapshot

Print a one-shot metrics table to stdout:

```bash
sentinel metrics snapshot
```

This is equivalent to `sentinel metrics export` without options.

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

MIT
