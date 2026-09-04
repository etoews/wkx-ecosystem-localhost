"""The test HTTP client, built to clear the board's Host guard.

The board refuses any request whose ``Host`` is not a bound loopback name (the
DNS-rebinding defence, ADR 0001), on every route. So the test client speaks from
an allowed loopback origin. It reads the app's own allow-list rather than assuming
a port, so a client built for an app on any port still clears the guard. A test
that needs to prove the guard refuses a foreign ``Host`` overrides the header on
the one request.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient


def loopback_client(app: FastAPI) -> TestClient:
    """A ``TestClient`` whose ``Host`` clears the app's own loopback guard."""
    host = next(h for h in sorted(app.state.allowed_hosts) if h.startswith("127.0.0.1:"))
    return TestClient(app, base_url=f"http://{host}")
