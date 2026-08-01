"""Server-Sent Events framing for the fetch stream.

The transport that carries each fetch result to the board, kept tiny and
separate from the Collector: the Collector yields typed events, this wraps them
in the wire format the browser's native ``EventSource`` consumes. No third-party
library is involved on either end.
"""

from __future__ import annotations

from wkx_ecosystem_localhost.models import FetchEvent

# Media type for the streaming response.
EVENT_STREAM = "text/event-stream"


def pack(event: FetchEvent) -> str:
    """Frame one fetch result as an SSE ``data:`` message."""
    return f"data: {event.model_dump_json()}\n\n"


def done() -> str:
    """Frame the terminal event so the client closes rather than reconnecting.

    A native ``EventSource`` reopens the connection when a stream ends. Emitting
    a named ``done`` event lets the board close the source itself once every repo
    has reported, so the one-write fetch runs exactly once per page load instead
    of looping.
    """
    return "event: done\ndata: {}\n\n"
