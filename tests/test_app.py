"""Board shell and health checks over the HTTP API."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_index_serves_the_board(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "WKX" in response.text
    assert "localhost" in response.text


def test_index_carries_the_six_sections(client: TestClient) -> None:
    response = client.get("/")

    for section in ("workspace", "toolchains", "claude", "system", "homebrew", "docker"):
        assert section in response.text


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


def test_the_shell_and_assets_revalidate_so_the_browser_never_runs_stale_code(
    client: TestClient,
) -> None:
    # The board is a live dashboard, often run under serve --reload; without
    # no-cache a browser can keep running an old app.js after a change, so a
    # newly added panel never fills. The shell and every static asset must carry
    # Cache-Control: no-cache so each load revalidates (unchanged files still 304).
    for path in ("/", "/static/app.js", "/static/styles.css"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers.get("cache-control") == "no-cache", path
