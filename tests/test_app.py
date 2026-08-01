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
