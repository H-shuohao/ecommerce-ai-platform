import asyncio
import json
from typing import Any


MAX_STREAM_OUTPUT_CHARS = 400


def chunk_to_sse_json(chunk: Any) -> str | None:
    """Convert an SDK stream chunk to an SSE-compatible JSON payload."""
    if chunk is None:
        return None

    model_dump_json = getattr(chunk, "model_dump_json", None)
    if callable(model_dump_json):
        return str(model_dump_json())

    if isinstance(chunk, str):
        return chunk

    return json.dumps(chunk, ensure_ascii=False, default=str)


def chunk_delta_content(chunk: Any) -> str:
    """Read the generated text from an OpenAI-compatible stream chunk."""
    choices = getattr(chunk, "choices", None)
    if not choices:
        return ""

    delta = getattr(choices[0], "delta", None)
    content = getattr(delta, "content", None)
    return content or ""


def chunk_usage(chunk: Any) -> Any:
    return getattr(chunk, "usage", None)


def usage_value(usage: Any, name: str) -> Any:
    return getattr(usage, name, "?")


def should_stop_streaming(text: str) -> bool:
    return len(text.strip()) >= MAX_STREAM_OUTPUT_CHARS


async def next_from_sync_iterator(iterator: Any, sentinel: Any) -> Any:
    """Read a synchronous SDK iterator without blocking the event loop."""
    return await asyncio.to_thread(next, iterator, sentinel)

