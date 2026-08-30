"""Server-Sent Events framing for the fetch stream.

The transport that carries each fetch result to the board, kept tiny and
separate from the Collector: the Collector yields typed events, this wraps them
in the wire format the browser's native ``EventSource`` consumes. No third-party
library is involved on either end.
"""

from __future__ import annotations

from pydantic import BaseModel

# Media type for the streaming response.
EVENT_STREAM = "text/event-stream"


def pack(event: BaseModel) -> str:
    """Frame one streamed result as an SSE ``data:`` message.

    Any of the board's event models (a repo's fetch result, a submodule's remote
    tags) serialises the same way, so this stays generic over the model rather
    than naming one, and every stream shares the one wire format.
    """
    return f"data: {event.model_dump_json()}\n\n"


def pack_event(name: str, event: BaseModel) -> str:
    """Frame one streamed result as a named SSE event, for a client listener.

    The default message the browser dispatches on the unnamed ``message`` event is
    fine for a single-purpose stream, but a stream that carries more than one kind
    of update names each so the board can listen for the one it wants. The View
    convergence stream uses this to push a ``view`` event that every open tab
    applies (ADR 0004).
    """
    return f"event: {name}\ndata: {event.model_dump_json()}\n\n"


def comment(text: str) -> str:
    """Frame an SSE comment line, used as a keep-alive that no listener sees.

    A colon-led line is ignored by the browser's ``EventSource`` but keeps the
    connection warm and flushes the response so the stream opens promptly.
    """
    return f": {text}\n\n"


def done() -> str:
    """Frame the terminal event so the client closes rather than reconnecting.

    A native ``EventSource`` reopens the connection when a stream ends. Emitting
    a named ``done`` event lets the board close the source itself once every repo
    has reported, so the one-write fetch runs exactly once per page load instead
    of looping.
    """
    return "event: done\ndata: {}\n\n"
