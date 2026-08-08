# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright"]
# ///
"""Playwright verification of the M8 token highlight, pin, and release.

A durable, hands-on artefact for M8 (token-highlighting). It is NOT a CI test and
is deliberately kept out of the pytest suite: it drives a real browser against a
live board, which needs Chrome and a running server. It proves the three things
the milestone promises, end to end in a browser:

  a. Hovering a value that recurs lights every matching cell across panels.
  b. Clicking pins the highlight, and it survives the pointer leaving.
  c. Esc releases the pin and the board goes quiet again.

The board inventories THIS machine, so its rendered values and any screenshot are
real machine data. Screenshots are written outside the repo (a temp dir) and must
never be committed to this public, machine-neutral repository.

Run it (from the repo root):

    uv run --with playwright playwright install chromium   # one-time browser fetch
    uv run artefacts/pin_highlight_playwright.py

By default it launches its own board on an unused loopback port and stops it on
exit. To drive a board you already have running, point it at one:

    WKX_BASE_URL=http://127.0.0.1:8787 uv run artefacts/pin_highlight_playwright.py

Screenshots land in ${TMPDIR}/wkx-pin/ (lit.png, pinned.png, cleared.png) unless
WKX_SHOT_DIR overrides it. Exit status is 0 on PASS, 1 on FAIL.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

SHOT_DIR = Path(os.environ.get("WKX_SHOT_DIR") or (Path(tempfile.gettempdir()) / "wkx-pin"))


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _healthy(base: str, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(base + "/api/health", timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            # Polling: any failure just means the board is not up yet.
            time.sleep(0.25)
    return False


def _launch_board() -> tuple[str, subprocess.Popen[bytes] | None]:
    """Return (base_url, process). process is None when reusing an external board."""
    external = os.environ.get("WKX_BASE_URL")
    if external:
        base = external.rstrip("/")
        if not _healthy(base):
            sys.exit(f"WKX_BASE_URL={base} is not answering /api/health")
        return base, None

    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        ["uv", "run", "wkx-ecosystem-localhost", "serve", "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if not _healthy(base):
        proc.terminate()
        sys.exit("the board never became healthy; run it by hand to see why")
    return base, proc


# A token's identity and current highlight state, read straight off the DOM.
_STATE_JS = """
() => {
  const cells = Array.from(document.querySelectorAll('[data-token-kind]'));
  const groups = {};
  for (const c of cells) {
    const id = c.dataset.tokenKind + '|' + c.dataset.tokenValue;
    (groups[id] ||= []).push(c);
  }
  return {
    match: document.querySelectorAll('.tok-match').length,
    origin: document.querySelectorAll('.tok-origin').length,
    pinned: document.querySelectorAll('.tok-pinned').length,
    pressed: document.querySelectorAll('[data-token-kind][aria-pressed=\"true\"]').length,
    groupSizes: Object.fromEntries(Object.entries(groups).map(([k, v]) => [k, v.length])),
  };
}
"""


def _state(page: Page) -> dict:
    return page.evaluate(_STATE_JS)


def _pick_recurring(page: Page) -> tuple[str, str]:
    """A (kind, value) present in at least two token cells, so a highlight spans."""
    sizes: dict[str, int] = _state(page)["groupSizes"]
    for identity, count in sizes.items():
        if count >= 2:
            kind, value = identity.split("|", 1)
            return kind, value
    sys.exit("no value recurs across the board on this machine; cannot demonstrate matching")


def main() -> int:
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    base, proc = _launch_board()
    failures: list[str] = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 2200})
            page.goto(base + "/", wait_until="networkidle")
            page.wait_for_selector("[data-token-kind][data-token-ready]", timeout=15000)
            # Let the SSE-filled version/latest cells settle so more values recur.
            page.wait_for_timeout(1500)

            kind, value = _pick_recurring(page)
            sel = f'[data-token-kind="{kind}"][data-token-value="{value}"]'
            cells = page.locator(sel)
            total = cells.count()
            print(f"chosen token: kind={kind!r} value={value!r} occurs {total}x")

            # (a) Hover lights every matching cell; the origin is the stronger one.
            cells.first.hover()
            page.wait_for_timeout(200)
            lit = _state(page)
            page.screenshot(path=str(SHOT_DIR / "lit.png"), full_page=True)
            if lit["match"] + lit["origin"] != total or lit["origin"] < 1:
                failures.append(f"(a) hover lit {lit['match']}+{lit['origin']} of {total} cells")
            if lit["pinned"] != 0:
                failures.append("(a) hover should not pin anything yet")

            # (b) Click pins it; moving the pointer away keeps it lit.
            cells.first.click()
            page.wait_for_timeout(150)
            page.mouse.move(4, 4)  # leave the token; a transient highlight would clear here
            page.wait_for_timeout(250)
            pinned = _state(page)
            page.screenshot(path=str(SHOT_DIR / "pinned.png"), full_page=True)
            if pinned["match"] + pinned["origin"] != total:
                failures.append(f"(b) pin lost matches after pointer-leave: {pinned}")
            if pinned["pinned"] != 1 or pinned["pressed"] != 1:
                failures.append(f"(b) pin state not committed to AT: {pinned}")

            # (c) Esc releases the pin; the board goes quiet.
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)
            cleared = _state(page)
            page.screenshot(path=str(SHOT_DIR / "cleared.png"), full_page=True)
            if any(cleared[k] for k in ("match", "origin", "pinned", "pressed")):
                failures.append(f"(c) Esc did not clear the highlight: {cleared}")

            browser.close()
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    print(f"screenshots -> {SHOT_DIR}/  (real machine data; do not commit)")
    if failures:
        print("FAIL")
        for line in failures:
            print("  - " + line)
        return 1
    print("PASS: hover lights matches, click pins through pointer-leave, Esc clears")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
