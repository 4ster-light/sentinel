from datetime import datetime
from pathlib import Path

from sentinel.state import PortInfo, ProcessInfo, State, get_log_paths


class TestProcessInfo:
	def test_to_dict(self):
		info = ProcessInfo(
			id=1,
			pid=12345,
			name="test",
			cmd="echo hello",
			cwd="/tmp",
			restart=True,
			started_at="2024-01-01T00:00:00",
			stdout_log="/tmp/test.stdout.log",
			stderr_log="/tmp/test.stderr.log",
			env={"VAR": "value"},
		)

		data = info.to_dict()

		assert data["id"] == 1
		assert data["pid"] == 12345
		assert data["name"] == "test"
		assert data["cmd"] == "echo hello"
		assert data["cwd"] == "/tmp"
		assert data["restart"] is True
		assert data["started_at"] == "2024-01-01T00:00:00"
		assert data["stdout_log"] == "/tmp/test.stdout.log"
		assert data["stderr_log"] == "/tmp/test.stderr.log"
		assert data["env"] == {"VAR": "value"}

	def test_from_dict(self):
		data = {
			"id": 1,
			"pid": 12345,
			"name": "test",
			"cmd": "echo hello",
			"cwd": "/tmp",
			"restart": True,
			"started_at": "2024-01-01T00:00:00",
			"stdout_log": "/tmp/test.stdout.log",
			"stderr_log": "/tmp/test.stderr.log",
			"env": {"VAR": "value"},
		}

		info = ProcessInfo.from_dict(data)

		assert info.id == 1
		assert info.pid == 12345
		assert info.name == "test"
		assert info.cmd == "echo hello"
		assert info.cwd == "/tmp"
		assert info.restart is True
		assert info.started_at == "2024-01-01T00:00:00"
		assert info.stdout_log == "/tmp/test.stdout.log"
		assert info.stderr_log == "/tmp/test.stderr.log"
		assert info.env == {"VAR": "value"}

	def test_from_dict_without_env(self):
		data = {
			"id": 1,
			"pid": 12345,
			"name": "test",
			"cmd": "echo hello",
			"cwd": "/tmp",
			"restart": False,
			"started_at": "2024-01-01T00:00:00",
			"stdout_log": "/tmp/test.stdout.log",
			"stderr_log": "/tmp/test.stderr.log",
		}

		info = ProcessInfo.from_dict(data)

		assert info.env == {}


class TestPortInfo:
	def test_to_dict(self):
		info = PortInfo(port=8080, name="webapp", allocated_at="2024-01-01T00:00:00")

		data = info.to_dict()

		assert data["port"] == 8080
		assert data["name"] == "webapp"
		assert data["allocated_at"] == "2024-01-01T00:00:00"

	def test_from_dict(self):
		data = {"port": 8080, "name": "webapp", "allocated_at": "2024-01-01T00:00:00"}

		info = PortInfo.from_dict(data)

		assert info.port == 8080
		assert info.name == "webapp"
		assert info.allocated_at == "2024-01-01T00:00:00"


class TestState:
	def test_init(self, state: State):
		assert state.processes == {}
		assert state.ports == {}
		assert state.next_id == 1

	def test_get_next_id(self, state: State):
		id1 = state.get_next_id()
		id2 = state.get_next_id()
		id3 = state.get_next_id()

		assert id1 == 1
		assert id2 == 2
		assert id3 == 3
		assert state.next_id == 4

	def test_add_process(self, state: State):
		info = ProcessInfo(
			id=1,
			pid=12345,
			name="test",
			cmd="echo hello",
			cwd="/tmp",
			restart=False,
			started_at=datetime.now().isoformat(),
			stdout_log="/tmp/test.stdout.log",
			stderr_log="/tmp/test.stderr.log",
		)

		state.add_process(info)

		assert 1 in state.processes
		assert state.processes[1].name == "test"

	def test_get_process(self, state: State):
		info = ProcessInfo(
			id=1,
			pid=12345,
			name="test",
			cmd="echo hello",
			cwd="/tmp",
			restart=False,
			started_at=datetime.now().isoformat(),
			stdout_log="/tmp/test.stdout.log",
			stderr_log="/tmp/test.stderr.log",
		)

		state.add_process(info)

		retrieved = state.get_process(1)
		assert retrieved is not None
		assert retrieved.name == "test"

		not_found = state.get_process(999)
		assert not_found is None

	def test_find_process_by_name(self, state: State):
		info = ProcessInfo(
			id=1,
			pid=12345,
			name="myapp",
			cmd="echo hello",
			cwd="/tmp",
			restart=False,
			started_at=datetime.now().isoformat(),
			stdout_log="/tmp/test.stdout.log",
			stderr_log="/tmp/test.stderr.log",
		)

		state.add_process(info)

		found = state.find_process_by_name("myapp")
		assert found is not None
		assert found.id == 1

		not_found = state.find_process_by_name("nonexistent")
		assert not_found is None

	def test_remove_process(self, state: State):
		info = ProcessInfo(
			id=1,
			pid=12345,
			name="test",
			cmd="echo hello",
			cwd="/tmp",
			restart=False,
			started_at=datetime.now().isoformat(),
			stdout_log="/tmp/test.stdout.log",
			stderr_log="/tmp/test.stderr.log",
		)

		state.add_process(info)
		assert 1 in state.processes

		removed = state.remove_process(1)
		assert removed is not None
		assert removed.name == "test"
		assert 1 not in state.processes

		removed_again = state.remove_process(1)
		assert removed_again is None

	def test_list_processes(self, state: State):
		info1 = ProcessInfo(
			id=1,
			pid=12345,
			name="proc1",
			cmd="echo 1",
			cwd="/tmp",
			restart=False,
			started_at=datetime.now().isoformat(),
			stdout_log="/tmp/test1.stdout.log",
			stderr_log="/tmp/test1.stderr.log",
		)
		info2 = ProcessInfo(
			id=2,
			pid=12346,
			name="proc2",
			cmd="echo 2",
			cwd="/tmp",
			restart=False,
			started_at=datetime.now().isoformat(),
			stdout_log="/tmp/test2.stdout.log",
			stderr_log="/tmp/test2.stderr.log",
		)

		state.add_process(info1)
		state.add_process(info2)

		processes = state.list_processes()
		assert len(processes) == 2

		names = {p.name for p in processes}
		assert names == {"proc1", "proc2"}

	def test_allocate_port_auto(self, state: State):
		port = state.allocate_port("webapp")

		assert port is not None
		assert 1024 <= port <= 65535
		assert port in state.ports
		assert state.ports[port].name == "webapp"

	def test_allocate_port_specific(self, state: State):
		# Find an available port first
		import socket

		sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		sock.bind(("127.0.0.1", 0))
		available_port = sock.getsockname()[1]
		sock.close()

		port = state.allocate_port("webapp", available_port)

		assert port == available_port
		assert port in state.ports
		assert state.ports[port].name == "webapp"

	def test_allocate_port_duplicate(self, state: State):
		import socket

		sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		sock.bind(("127.0.0.1", 0))
		available_port = sock.getsockname()[1]
		sock.close()

		port1 = state.allocate_port("webapp", available_port)
		assert port1 == available_port

		port2 = state.allocate_port("other", available_port)
		assert port2 is None

	def test_free_port(self, state: State):
		port = state.allocate_port("webapp")
		assert port is not None
		assert port in state.ports

		freed = state.free_port(port)
		assert freed is True
		assert port not in state.ports

		freed_again = state.free_port(port)
		assert freed_again is False

	def test_get_port(self, state: State):
		port = state.allocate_port("webapp")
		assert port is not None

		info = state.get_port(port)
		assert info is not None
		assert info.port == port
		assert info.name == "webapp"

		not_found = state.get_port(99999)
		assert not_found is None

	def test_list_ports(self, state: State):
		_port1 = state.allocate_port("webapp")
		_port2 = state.allocate_port("api")
		_port3 = state.allocate_port("webapp")

		all_ports = state.list_ports()
		assert len(all_ports) == 3

		webapp_ports = state.list_ports(name="webapp")
		assert len(webapp_ports) == 2
		assert all(p.name == "webapp" for p in webapp_ports)

		api_ports = state.list_ports(name="api")
		assert len(api_ports) == 1
		assert api_ports[0].name == "api"

	def test_save_and_load(self, state: State, temp_state_dir: Path):
		# Add a process
		info = ProcessInfo(
			id=1,
			pid=12345,
			name="test",
			cmd="echo hello",
			cwd="/tmp",
			restart=True,
			started_at="2024-01-01T00:00:00",
			stdout_log="/tmp/test.stdout.log",
			stderr_log="/tmp/test.stderr.log",
			env={"VAR": "value"},
		)
		state.add_process(info)

		# Allocate a port
		_port = state.allocate_port("webapp", 8080)

		# Update next_id
		state.get_next_id()

		# Create a new State instance to load from disk
		new_state = State()

		# Verify loaded state (next_id should be 2: started at 1, incremented once)
		assert new_state.next_id == 2
		assert 1 in new_state.processes
		assert new_state.processes[1].name == "test"
		assert new_state.processes[1].env == {"VAR": "value"}
		assert 8080 in new_state.ports
		assert new_state.ports[8080].name == "webapp"


class TestHelperFunctions:
	def test_get_log_paths(self):
		stdout, stderr = get_log_paths("myapp")

		assert stdout.name == "myapp.stdout.log"
		assert stderr.name == "myapp.stderr.log"
		assert stdout.parent == stderr.parent

	def test_get_log_paths_sanitization(self):
		stdout, stderr = get_log_paths("my app/with:special*chars?")

		# Should sanitize special characters
		assert stdout.name == "my_app_with_special_chars_.stdout.log"
		assert stderr.name == "my_app_with_special_chars_.stderr.log"
