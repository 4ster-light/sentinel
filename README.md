# Sentinel

A lightweight process supervisor CLI for managing background processes with
ease.

## Features

- **Start & manage processes**: Run background processes with automatic logging
- **Process monitoring**: Real-time CPU, memory, and uptime tracking
- **Auto-restart**: Optional automatic restart on process exit
- **Port management**: Check and manage port usage
- **Rich output**: Beautiful formatted tables and logs with rich CLI
- **Persistent state**: Track processes across sessions

## Installation

Clone the repository and install from source:

```bash
git clone https://github.com/4ster-light/sentinel
cd sentinel
uv sync
```

Then install the package system wide:

```bash
uv tool install .
```

## Quick Start

### Run a process

```bash
# Start a background process
sentinel run "python server.py" --name myserver

# Start with auto-restart enabled
sentinel run "npm start" --name frontend --restart
```

### List processes

```bash
# View all managed processes with status
sentinel list
```

### Control processes

```bash
# Stop a process by ID or name
sentinel stop myserver

# Force kill a process
sentinel stop myserver --force

# Restart a process
sentinel restart myserver
```

### View logs

```bash
# Show process logs
sentinel logs myserver

# Clear logs
sentinel logs myserver --clear
```

### Port management

```bash
# Allocate a port
sentinel port allocate

# List allocated ports
sentinel port list

# Free an allocated port
sentinel port free 8000
```

## Usage

```bash
sentinel --help
```

For detailed help on any command:

```bash
sentinel <command> --help
```

## License

MIT
