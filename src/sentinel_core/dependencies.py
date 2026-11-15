"""Dependency-aware ordering for process start and stop"""

from collections.abc import Collection, Sequence

from .models import ProcessInfo


class DependencyError(ValueError):
	"""Raised when a dependency graph cannot be satisfied."""


def start_order(
	processes: Sequence[ProcessInfo],
	*,
	available: Collection[str] = (),
	strict: bool = True,
) -> list[ProcessInfo]:
	"""Return *processes* ordered so every dependency comes before its dependents.

	Dependencies are matched by process name. A dependency that is not part of
	*processes* is accepted when it is listed in *available*, which callers use
	for processes that are already running. With ``strict=False`` unknown
	dependencies are ignored, which is what stop ordering needs.

	Independent processes keep their input order, so the result is stable.
	"""
	by_name = _index_by_name(processes)
	dependents: dict[str, list[str]] = {name: [] for name in by_name}
	pending: dict[str, int] = {name: 0 for name in by_name}

	for process in processes:
		for dependency in dict.fromkeys(process.depends_on):
			if dependency in by_name:
				dependents[dependency].append(process.name)
				pending[process.name] += 1
			elif strict and dependency not in available:
				raise DependencyError(
					f"Process '{process.name}' depends on '{dependency}', which is neither in this batch nor running"
				)

	ready = [process for process in processes if pending[process.name] == 0]
	ordered: list[ProcessInfo] = []
	while ready:
		process = ready.pop(0)
		ordered.append(process)
		for dependent_name in dependents[process.name]:
			pending[dependent_name] -= 1
			if pending[dependent_name] == 0:
				ready.append(by_name[dependent_name])

	if len(ordered) != len(processes):
		cycle = _find_cycle({name for name, count in pending.items() if count > 0}, dependents)
		raise DependencyError(f"Dependency cycle: {' -> '.join(cycle)}")
	return ordered


def stop_order(processes: Sequence[ProcessInfo]) -> list[ProcessInfo]:
	"""Return *processes* ordered so dependents stop before their dependencies.

	A dependency cycle has no valid order, and a process graph that cannot be
	ordered must still be stoppable, so the input order is used as a fallback.
	"""
	try:
		return list(reversed(start_order(processes, strict=False)))
	except DependencyError:
		return list(processes)


def _index_by_name(processes: Sequence[ProcessInfo]) -> dict[str, ProcessInfo]:
	by_name: dict[str, ProcessInfo] = {}
	for process in processes:
		if process.name in by_name:
			raise DependencyError(f"Duplicate process name '{process.name}' in the dependency graph")
		if process.name in process.depends_on:
			raise DependencyError(f"Process '{process.name}' cannot depend on itself")
		by_name[process.name] = process
	return by_name


def _find_cycle(nodes: set[str], dependents: dict[str, list[str]]) -> list[str]:
	"""Return one cycle among *nodes* for the error message, or the node names."""
	visited: dict[str, int] = {}
	path: list[str] = []

	def walk(node: str) -> list[str] | None:
		visited[node] = 1
		path.append(node)
		for dependent in dependents[node]:
			if dependent not in nodes:
				continue
			if visited.get(dependent, 0) == 1:
				return [*path[path.index(dependent) :], dependent]
			if visited.get(dependent, 0) == 0:
				found = walk(dependent)
				if found is not None:
					return found
		visited[node] = 2
		path.pop()
		return None

	for node in sorted(nodes):
		if visited.get(node, 0) == 0:
			found = walk(node)
			if found is not None:
				return found
	return sorted(nodes)
