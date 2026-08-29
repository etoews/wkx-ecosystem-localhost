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


def test_styles_are_served_with_wkx_tokens(client: TestClient) -> None:
    response = client.get("/static/styles.css")

    assert response.status_code == 200
    assert "--deep" in response.text
    assert "wkx-namespace" in response.text


def test_app_js_persists_theme_choice(client: TestClient) -> None:
    response = client.get("/static/app.js")

    assert response.status_code == 200
    assert "wkx-theme" in response.text


def test_app_js_persists_hidden_sections(client: TestClient) -> None:
    # The sections menu keeps its Hidden overrides in localStorage the way the theme
    # toggle keeps its choice; this pins the key the way wkx-theme is pinned.
    response = client.get("/static/app.js")

    assert response.status_code == 200
    assert "wkx-sections" in response.text


def test_app_js_persists_collapsed_panels(client: TestClient) -> None:
    # A Collapsed panel is a client-side view preference kept in localStorage the
    # way the theme choice and the Hidden overrides are; this pins the key the way
    # wkx-theme and wkx-sections are pinned.
    response = client.get("/static/app.js")

    assert response.status_code == 200
    assert "wkx-collapsed" in response.text


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
