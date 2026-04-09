"""Compatibility aliases for the legacy Sentinel package."""

from importlib import import_module
from types import ModuleType
import sys


def _alias(old_name: str, new_name: str) -> ModuleType:
	module = import_module(new_name)
	sys.modules[old_name] = module
	return module


process = _alias(f"{__name__}.process", "sentinel_core.process")
state = _alias(f"{__name__}.state", "sentinel_core.state")
env = _alias(f"{__name__}.env", "sentinel_core.env")
logs = _alias(f"{__name__}.logs", "sentinel_core.logs")
health = _alias(f"{__name__}.health", "sentinel_core.health")
restart_monitor = _alias(f"{__name__}.restart_monitor", "sentinel_core.restart_monitor")
cli = _alias(f"{__name__}.cli", "sentinel_cli")
_alias(f"{__name__}.cli.main", "sentinel_cli.main")
_alias(f"{__name__}.cli.daemon", "sentinel_cli.daemon")
_alias(f"{__name__}.cli.group", "sentinel_cli.group")
_alias(f"{__name__}.cli.port", "sentinel_cli.port")

__all__ = ["cli", "env", "health", "logs", "process", "restart_monitor", "state"]
