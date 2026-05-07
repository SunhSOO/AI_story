import json
from collections.abc import AsyncIterable
from typing import Any

from starlette.responses import StreamingResponse


def _format_sse(message: Any) -> str:
    if isinstance(message, dict):
        event = message.get("event")
        data = message.get("data", "")
        event_id = message.get("id")
        retry = message.get("retry")
    else:
        event = None
        data = message
        event_id = None
        retry = None

    if not isinstance(data, str):
        data = json.dumps(data, ensure_ascii=False)

    lines: list[str] = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    if event is not None:
        lines.append(f"event: {event}")
    if retry is not None:
        lines.append(f"retry: {retry}")

    for line in data.splitlines() or [""]:
        lines.append(f"data: {line}")

    return "\n".join(lines) + "\n\n"


class EventSourceResponse(StreamingResponse):
    """Small local fallback for the subset of sse-starlette used by this app."""

    media_type = "text/event-stream"

    def __init__(self, content: AsyncIterable[Any], **kwargs: Any) -> None:
        headers = {
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
        headers.update(kwargs.pop("headers", {}) or {})
        super().__init__(
            self._stream(content),
            media_type=self.media_type,
            headers=headers,
            **kwargs,
        )

    async def _stream(self, content: AsyncIterable[Any]):
        async for message in content:
            yield _format_sse(message).encode("utf-8")
