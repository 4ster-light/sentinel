# Sentinel

A lightweight process supervisor CLI for managing background processes.

## Features

- Start and manage background processes with automatic logging
- Real-time CPU, memory, and uptime monitoring
- Automatic restart on process crash or exit
- Process groups for organizing related processes
- Port allocation and management
- Persistent state across sessions

## Installation

Using [uv](https://docs.astral.sh/uv) (recommended):

```bash
uv tool install git+https://github.com/4ster-light/sentinel
```

Using pip:

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

## Process Management

### Starting a Process

Start a background process with `sentinel run`:

```bash
# Basic usage
sentinel run "python server.py"

# Give the process a name for easier reference
sentinel run "python server.py" --name myserver

# Enable auto-restart on crash or exit
sentinel run "npm start" --name frontend --restart

# Add process to a group
sentinel run "python worker.py" --name worker1 --group workers

# Use environment variables from a file
sentinel run "node app.js" --name app --env-file .env
```

When you use `--restart` without the daemon running, you will see a warning:

```txt
Started myserver (id: 1, pid: 12345)
Warning: Restart flag set but daemon is not running. Restarts will only happen
when you run other sentinel commands.
  Run 'sentinel daemon start' for continuous monitoring.
```

### Listing Processes

View all managed processes:

```bash
sentinel list
```

Output shows a table with ID, name, PID, status, CPU usage, memory usage,
uptime, restart flag, group, and command:

```txt
+----+----------+-------+---------+------+-------+--------+---------+-------+-----------+
| ID | NAME     |   PID | STATUS  |  CPU |   MEM | UPTIME | RESTART | GROUP | COMMAND   |
+----+----------+-------+---------+------+-------+--------+---------+-------+-----------+
|  1 | myserver | 12345 | running | 2.1% | 45 MB |   5m 3s|    -    |   -   | python ...|
|  2 | frontend | 12346 | running | 0.5% | 120MB |   2m 1s|    X    |   -   | npm start |
+----+----------+-------+---------+------+-------+--------+---------+-------+-----------+
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
restarts them automatically in the background.

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

## Configuration

Sentinel stores its state in `~/.sentinel/`:

- `state.json` - Process registry and port allocations
- `logs/` - Process stdout and stderr logs
- `daemon.pid` - PID file for the restart daemon

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
```

## License

MIT
