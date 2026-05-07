"""SSE event emission helpers."""
import asyncio
import json
from collections import defaultdict
from typing import AsyncGenerator


class EventBus:
    """Per-run async event queues for SSE streaming."""

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)

    async def emit(self, run_id: str, data: dict) -> None:
        await self._queues[run_id].put(data)

    async def stream(self, run_id: str) -> AsyncGenerator[dict, None]:
        queue = self._queues[run_id]
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield event
                status = event.get("status", "")
                if status in ("DONE", "FAILED"):
                    break
            except asyncio.TimeoutError:
                yield {"keepalive": True}

    def cleanup(self, run_id: str) -> None:
        self._queues.pop(run_id, None)


event_bus = EventBus()
