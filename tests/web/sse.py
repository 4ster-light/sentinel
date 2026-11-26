"""Raw ASGI driver for the Server-Sent Events stream.

The starlette TestClient consumes a whole response before it returns, so it
cannot enter an infinite stream on every version this project builds
against. The stream tests drive the app through the ASGI interface instead
and cut it off once they collected the events they need.
"""

import asyncio
import contextlib
from collections.abc import Callable, MutableMapping
from typing import Any

from fastapi import FastAPI


class _EnoughEvents(Exception):
	"""Raised inside the send callable to end the app call."""


def read_events(
	app: FastAPI,
	count: int = 1,
	token: str | None = None,
	on_event: Callable[[str], None] | None = None,
) -> tuple[dict[str, Any], list[str]]:
	"""Collect the response start message and the first *count* event payloads."""
	start: dict[str, Any] = {}
	events: list[str] = []

	async def drive() -> None:
		requests = 0
		disconnected = asyncio.Event()

		async def receive() -> dict[str, Any]:
			nonlocal requests
			requests += 1
			if requests == 1:
				return {"type": "http.request", "body": b"", "more_body": False}
			# Hold the disconnect listener open until the events are collected.
			await disconnected.wait()
			return {"type": "http.disconnect"}

		async def send(message: MutableMapping[str, Any]) -> None:
			if message["type"] == "http.response.start":
				if not start:
					start.update(message)
				return
			if message["type"] != "http.response.body":
				return
			for chunk in message.get("body", b"").decode("utf-8").split("\n\n"):
				if not chunk.startswith("data: "):
					continue
				events.append(chunk.removeprefix("data: "))
				if on_event is not None:
					on_event(events[-1])
				if len(events) >= count:
					raise _EnoughEvents

		headers = [] if token is None else [(b"x-control-token", token.encode())]
		scope = {
			"type": "http",
			"asgi": {"version": "3.0"},
			"http_version": "1.1",
			"method": "GET",
			"scheme": "http",
			"path": "/events",
			"raw_path": b"/events",
			"query_string": b"",
			"headers": headers,
			"client": ("testclient", 50000),
			"server": ("testserver", 80),
		}
		with contextlib.suppress(_EnoughEvents):
			await app(scope, receive, send)

	try:
		asyncio.run(asyncio.wait_for(drive(), timeout=5))
	except TimeoutError:
		raise AssertionError("the event stream did not produce the requested events in time") from None
	return start, events
