"""Board shell and health checks over the HTTP API."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from wkx_ecosystem_localhost.app import ViewBroadcaster, write_is_allowed

_ALLOWED_HOSTS = frozenset({"127.0.0.1:8787", "localhost:8787", "[::1]:8787"})


def _guard(*, origin: str | None, sec_fetch_site: str | None) -> bool:
    """Run the write guard with a valid content type and Host, varying only the two."""
    return write_is_allowed(
        content_type="application/json",
        host="127.0.0.1:8787",
        origin=origin,
        sec_fetch_site=sec_fetch_site,
        allowed_hosts=_ALLOWED_HOSTS,
    )


def test_index_serves_the_board(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "WKX" in response.text
    assert "localhost" in response.text


@pytest.mark.parametrize(
    "section", ["workspace", "toolchains", "claude", "system", "homebrew", "docker"]
)
def test_index_carries_each_section(client: TestClient, section: str) -> None:
    assert section in client.get("/").text


def test_index_carries_the_config_section_last(client: TestClient) -> None:
    response = client.get("/")

    assert 'id="config"' in response.text
    # The config Section is last on the board, after git config.
    assert response.text.index('id="git-config"') < response.text.index('id="config"')


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


# ---------- the Host guard (DNS-rebinding defence, ADR 0001) ----------


def test_a_data_route_refuses_a_foreign_host(client: TestClient) -> None:
    # A DNS-rebound page reaches the board same-origin under its own name; every
    # read route refuses a Host that is not a bound loopback name, so the page
    # cannot read the inventory.
    response = client.get("/api/config", headers={"host": "attacker.example:8787"})

    assert response.status_code == 403


def test_the_shell_refuses_a_foreign_host(client: TestClient) -> None:
    response = client.get("/", headers={"host": "attacker.example:8787"})

    assert response.status_code == 403


def test_a_loopback_host_is_allowed(client: TestClient) -> None:
    # The board reaches itself as localhost as well as 127.0.0.1, always on the
    # bound port; both clear the guard.
    response = client.get("/api/config", headers={"host": "localhost:8787"})

    assert response.status_code == 200


# ---------- the write guard's Sec-Fetch-Site branch (finding 18) ----------


def test_no_origin_is_a_non_browser_client() -> None:
    # curl sends no Origin at all; the write is accepted.
    assert _guard(origin=None, sec_fetch_site=None) is True


def test_a_same_origin_origin_is_accepted() -> None:
    assert _guard(origin="http://127.0.0.1:8787", sec_fetch_site="cross-site") is True


@pytest.mark.parametrize(
    ("sec_fetch_site", "expected"),
    [
        ("same-origin", True),
        ("same-site", False),
        ("cross-site", False),
        ("none", False),  # a user-initiated navigation, never a page fetch: refused
    ],
)
def test_a_null_origin_falls_to_sec_fetch_site(sec_fetch_site: str, expected: bool) -> None:
    # Origin: null (a sandboxed frame, a data: page) does not match the loopback set,
    # so the request falls to the Sec-Fetch-Site check; only same-origin clears it.
    assert _guard(origin="null", sec_fetch_site=sec_fetch_site) is expected


def test_a_foreign_origin_with_no_sec_fetch_site_is_refused() -> None:
    assert _guard(origin="http://evil.example", sec_fetch_site=None) is False


# ---------- the convergence broadcaster's bounded queue (finding 20) ----------


def test_publish_drops_a_frame_for_a_full_subscriber_queue() -> None:
    # A wedged tab's queue must not grow without bound: publish drops the frame
    # rather than raising or buffering forever. Each frame is a full View snapshot,
    # so that tab simply resyncs from the next frame it reads.
    broadcaster = ViewBroadcaster()
    full: asyncio.Queue[str] = asyncio.Queue(maxsize=1)
    full.put_nowait("already here")
    broadcaster._subscribers.add(full)

    broadcaster.publish("new frame")  # must not raise

    assert full.qsize() == 1  # the new frame was dropped, not queued behind the first


def test_styles_are_served_with_wkx_tokens(client: TestClient) -> None:
    response = client.get("/static/styles.css")

    assert response.status_code == 200
    assert "--deep" in response.text
    assert "wkx-namespace" in response.text


def test_app_js_persists_no_preference_to_localstorage(client: TestClient) -> None:
    # The View file is the only store (ADR 0004): the theme, the Hidden and
    # Collapsed panels, and the Mutes all live there, and localStorage is not used
    # at all — neither the board's JavaScript nor the served shell names it.
    assert "localStorage" not in client.get("/static/app.js").text
    assert "localStorage" not in client.get("/").text


def test_app_js_writes_view_preferences_through_the_api(client: TestClient) -> None:
    # Each change is written to the View through PATCH /api/view, not localStorage;
    # this pins the write path the way the localStorage keys were pinned before.
    response = client.get("/static/app.js")

    assert response.status_code == 200
    assert "/api/view" in response.text
    assert 'method: "PATCH"' in response.text


def test_index_carries_the_sections_menu(client: TestClient) -> None:
    response = client.get("/")

    assert 'id="sections-toggle"' in response.text
    assert 'id="sections-menu"' in response.text


@pytest.mark.parametrize("path", ["/", "/static/app.js", "/static/styles.css"])
def test_the_shell_and_assets_revalidate_so_the_browser_never_runs_stale_code(
    client: TestClient, path: str
) -> None:
    # The board is a live dashboard, often run under serve --reload; without
    # no-cache a browser can keep running an old app.js after a change, so a
    # newly added panel never fills. The shell and every static asset must carry
    # Cache-Control: no-cache so each load revalidates (unchanged files still 304).
    response = client.get(path)

    assert response.status_code == 200
    assert response.headers.get("cache-control") == "no-cache"
