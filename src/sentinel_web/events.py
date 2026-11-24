"""Server-sent events for the dashboard stream"""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import suppress


class EventBroadcaster:
	"""One sample pass per tick feeds every connected tab.

	*sample* returns a complete event payload as a string. The broadcaster
	runs it off the event loop, caches the latest payload for new tabs and
	hands the same payload to every connected queue.
	"""

	def __init__(self, sample: Callable[[], str], *, interval: float = 2.0) -> None:
		self._sample = sample
		self._interval = interval
		self._subscribers: set[asyncio.Queue[str]] = set()
		self._latest: str | None = None
		self._sampler: asyncio.Task[None] | None = None

	async def subscribe(self) -> asyncio.Queue[str]:
		"""A queue fed from every pass; a new tab first sees the latest payload."""
		if self._latest is None:
			self._latest = await asyncio.to_thread(self._sample)
		queue: asyncio.Queue[str] = asyncio.Queue()
		queue.put_nowait(self._latest)
		self._subscribers.add(queue)
		if self._sampler is None or self._sampler.done():
			self._sampler = asyncio.create_task(self._run())
		return queue

	def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
		self._subscribers.discard(queue)

	async def stream(self) -> AsyncIterator[str]:
		"""Server-sent events: one payload per message."""
		queue = await self.subscribe()
		try:
			while True:
				yield f"data: {await queue.get()}\n\n"
		finally:
			self.unsubscribe(queue)

	async def close(self) -> None:
		"""Stop the sampler. A finished task is dropped without raising its error."""
		sampler = self._sampler
		self._sampler = None
		if sampler is not None and not sampler.done():
			sampler.cancel()
			with suppress(asyncio.CancelledError):
				await sampler

	async def _run(self) -> None:
		while self._subscribers:
			await asyncio.sleep(self._interval)
			if not self._subscribers:
				break
			self._latest = await asyncio.to_thread(self._sample)
			for queue in list(self._subscribers):
				queue.put_nowait(self._latest)
