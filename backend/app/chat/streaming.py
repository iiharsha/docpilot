"""The AI SDK UI message stream, as bytes on the wire.

The only module that knows the format. One turn looks like this:

    data: {"type":"start","messageId":"…"}
    data: {"type":"text-start","id":"…"}
    data: {"type":"text-delta","id":"…","delta":"Gross "}
    data: {"type":"text-end","id":"…"}
    data: {"type":"finish"}
    data: [DONE]

Verified against `ai@7.0.107` (`UIMessageChunk` in `node_modules/ai/dist`).
`text-delta` carries `delta`, not `text`; the error part's key is `errorText`;
and `[DONE]` is what the SDK's own server sends, though its parser only skips
it. The `id` on the text parts scopes a block of text within one message, so a
single-block answer can reuse the message id.
"""

import json
from typing import Any

# Sent as response headers. `x-vercel-ai-ui-message-stream` is the protocol
# version the client is written against; `x-accel-buffering` asks a reverse
# proxy not to hold the body back, which would defeat streaming on Railway.
STREAM_HEADERS = {
    "x-vercel-ai-ui-message-stream": "v1",
    "cache-control": "no-cache",
    "x-accel-buffering": "no",
}

MEDIA_TYPE = "text/event-stream"

DONE = "data: [DONE]\n\n"


def start(message_id: str) -> dict[str, Any]:
    """Opens the assistant message."""
    return {"type": "start", "messageId": message_id}


def text_start(text_id: str) -> dict[str, Any]:
    return {"type": "text-start", "id": text_id}


def text_delta(text_id: str, delta: str) -> dict[str, Any]:
    return {"type": "text-delta", "id": text_id, "delta": delta}


def text_end(text_id: str) -> dict[str, Any]:
    return {"type": "text-end", "id": text_id}


def finish() -> dict[str, Any]:
    """Closes the assistant message. The client treats the turn as complete."""
    return {"type": "finish"}


def error(message: str) -> dict[str, Any]:
    """A failure the response status can no longer carry.

    `useChat` surfaces this on `error` and stops the turn.
    """
    return {"type": "error", "errorText": message}


def sse(part: dict[str, Any]) -> str:
    """Frame one part as a server-sent event.

    `ensure_ascii=False` keeps multi-byte characters intact rather than escaping
    them, and the blank line is what terminates an event.
    """
    return f"data: {json.dumps(part, ensure_ascii=False, separators=(',', ':'))}\n\n"
