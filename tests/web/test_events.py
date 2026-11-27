"""Tests for the dashboard Server-Sent Events stream"""

import asyncio
import json
from collections.abc import AsyncGenerator, Callable
from typing import cast

import pytest
from fastapi import FastAPI
from sse import read_events

from sentinel_core.models import ProcessInfo
from sentinel_core.state import State
from sentinel_web import create_dashboard_app
from sentinel_web.events import EventBroadcaster


@pytest.fixture
def live_app(state: State) -> FastAPI:
	return create_dashboard_app(lambda: state, event_interval=0.05)


class TestEventStream:
	def test_serves_the_process_state(self, live_app: FastAPI, spawn_process: Callable[..., ProcessInfo]) -> None:
		spawn_process("sleep 60", name="streamed", cluster="web", cluster_index=1)

		start, events = read_events(live_app, count=1)

		assert start["status"] == 200
		headers = {name.decode(): value.decode() for name, value in start["headers"]}
		assert headers["content-type"].startswith("text/event-stream")
		assert headers["cache-control"] == "no-cache"
		payload = json.loads(events[0])
		(row,) = payload["processes"]
		assert row["name"] == "streamed"
		assert row["cluster"] == "web"
		assert payload["updated_at"]

	def test_updates_arrive_on_change(self, live_app: FastAPI, spawn_process: Callable[..., ProcessInfo]) -> None:
		spawned: list[ProcessInfo] = []

		def after_the_seed(payload: str) -> None:
			if not spawned:
				spawned.append(spawn_process("sleep 60", name="late-joiner"))

		_start, events = read_events(live_app, count=2, on_event=after_the_seed)

		assert any(row["name"] == "late-joiner" for row in json.loads(events[1])["processes"])

	def test_reconnecting_client_gets_a_fresh_stream(self, live_app: FastAPI) -> None:
		first_start, first_events = read_events(live_app, count=1)
		second_start, second_events = read_events(live_app, count=1)

		assert first_start["status"] == 200
		assert second_start["status"] == 200
		assert json.loads(first_events[0])["updated_at"]
		assert json.loads(second_events[0])["updated_at"]


class TestEventBroadcaster:
	def test_one_pass_feeds_every_tab(self) -> None:
		async def scenario() -> None:
			samples: list[int] = []

			def sample() -> str:
				samples.append(len(samples))
				return json.dumps({"pass": len(samples)})

			broadcaster = EventBroadcaster(sample, interval=0.01)
			first = await broadcaster.subscribe()
			second = await broadcaster.subscribe()
			seed_first = await asyncio.wait_for(first.get(), 1)
			seed_second = await asyncio.wait_for(second.get(), 1)
			tick_first = await asyncio.wait_for(first.get(), 1)
			tick_second = await asyncio.wait_for(second.get(), 1)
			broadcaster.unsubscribe(first)
			broadcaster.unsubscribe(second)
			await broadcaster.close()

			assert seed_first == seed_second == json.dumps({"pass": 1})
			assert tick_first == tick_second == json.dumps({"pass": 2})
			assert len(samples) == 2

		asyncio.run(scenario())

	def test_sampling_stops_when_no_tab_is_connected(self) -> None:
		async def scenario() -> None:
			samples: list[str] = []

			def sample() -> str:
				samples.append("x")
				return "{}"

			broadcaster = EventBroadcaster(sample, interval=0.01)
			queue = await broadcaster.subscribe()
			await asyncio.wait_for(queue.get(), 1)
			broadcaster.unsubscribe(queue)
			await asyncio.sleep(0.1)
			await broadcaster.close()

			assert samples == ["x"]

		asyncio.run(scenario())


class TestBroadcasterDetails:
	def test_default_interval_is_two_seconds(self) -> None:
		assert EventBroadcaster(lambda: "{}")._interval == 2.0

	def test_close_cancels_the_sampler_and_clears_it(self) -> None:
		async def scenario() -> None:
			broadcaster = EventBroadcaster(lambda: "{}", interval=0.05)
			await broadcaster.subscribe()
			task = broadcaster._sampler
			assert task is not None

			await broadcaster.close()

			assert broadcaster._sampler is None
			assert task.done()
			assert task.cancelled()

		asyncio.run(scenario())

	def test_closing_the_stream_removes_its_queue(self) -> None:
		async def scenario() -> None:
			broadcaster = EventBroadcaster(lambda: "{}", interval=0.05)
			stream = cast(AsyncGenerator[str], broadcaster.stream())
			first = await stream.__anext__()
			assert first == "data: {}\n\n"
			assert len(broadcaster._subscribers) == 1

			await stream.aclose()

			assert broadcaster._subscribers == set()
			await broadcaster.close()

		asyncio.run(scenario())
