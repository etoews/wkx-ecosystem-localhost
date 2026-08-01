---
name: run-wkx-ecosystem-localhost
description: Run, serve, launch, smoke-test, and screenshot the WKX Ecosystem localhost board (the read-only FastAPI dashboard that inventories this dev machine). Use when asked to run, start, serve, drive, or screenshot the app, or to verify its API and UI end to end.
---

# Run: WKX Ecosystem localhost

A read-only board: a FastAPI app that serves a JSON API plus a static
HTML/JS page (no build step, native `EventSource` for progressive fill-in),
bound to `127.0.0.1:8787`. It inventories **this** machine, so the API
responses, the terminal output, and any screenshot contain real,
machine-specific data.

A bare run launches the app and **leaves it running** (a background `serve`) so
its output is visible. To verify it end to end, the `smoke.sh` driver launches
its own instance, curls every endpoint, checks the two SSE streams, screenshots
the board with headless Chrome, then stops. Paths below are relative to the repo
root.

## Prerequisites

macOS with these on `PATH` (all were already present here; install any that
are missing with Homebrew, and Google Chrome from google.com):

```sh
uv --version && curl --version | head -1 && jq --version && \
  ls "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
```

## Setup

```sh
uv sync
```

(First clone needs the submodule: `git clone --recurse-submodules <url>`.)

## Run (default) — launch and leave it running

A bare run should start the board and **leave it up**, with its output visible.
Launch `serve` as a background process. In Claude Code, run it with
`run_in_background` so the process persists and its log streams to a file you
can Read; the portable equivalent is `… serve > "$log" 2>&1 &`.

```sh
uv run wkx-ecosystem-localhost serve --port 8787
```

Confirm it is up:

```sh
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8787/api/health
```

The board is at `http://127.0.0.1:8787/`. The background log shows startup and
one access line per request, and is what "Claude Code can see the output" means
here:

```
Serving the board at http://127.0.0.1:8787/
INFO     uvicorn.error: Application startup complete.
INFO     uvicorn.error: Uvicorn running on http://127.0.0.1:8787 (Press CTRL+C to quit)
INFO     uvicorn.access: 127.0.0.1 - "GET /api/health HTTP/1.1" 200
```

It stays up until stopped. Stop it by killing the background task (Claude Code),
or portably:

```sh
pkill -f 'wkx-ecosystem-localhost serve'
```

## Smoke test — verify end to end

To check every endpoint and capture a screenshot in one shot. This launches its
own instance and **stops it on exit**, so use it for verification, not for a
session you want to keep open:

```sh
bash .claude/skills/run-wkx-ecosystem-localhost/smoke.sh 8788 "${TMPDIR:-/tmp}/wkx-board.png"
```

Both args are optional (`PORT` defaults to 8787, screenshot to
`$TMPDIR/wkx-board.png`). Verified output:

```
==> healthy
==> JSON endpoints
  ok    /api/health          "ok"
  ok    /api/workspace       "repos,roots"
  ok    /api/submodules      "submodules"
  ok    /api/toolchains      "node,python"
  ok    /api/system          "tools"
  ok    /api/claude          "mcp_servers,plugins,skills"
  ok    /api/homebrew        "casks,formulae,present"
  ok    /api/docker          "containers_running,containers_total,daemon_reachable,imag
  ok    /api/flags           "flags"
==> SSE endpoints  (a background git fetch runs; may take a few seconds)
  ok    /api/workspace/fetch frames=13
  ok    /api/submodules/probe frames=2
==> screenshot -> .../wkx-board.png  (contains real machine data; do not commit)
==> done (PASS); server stops on exit
```

Then **open the screenshot and look at it.** A correct board shows the masthead,
a "N want attention" tally, the workspace repos with branch and ahead/behind,
and the toolchains / claude / system / homebrew / docker panels. The screenshot
holds this machine's real inventory; it is written outside the repo on purpose.
**Never commit it** to this public, machine-neutral repo.

## Run (human path)

```sh
uv run wkx-ecosystem-localhost serve
```

Then open `http://127.0.0.1:8787`. Add `--open-browser` to open it
automatically, or `--port <n>` to bind elsewhere. Ctrl-C to stop. This is the
real product surface; headless, use the driver instead.

## Direct invocation (the layer most changes touch)

Every Collector is a pure function over the `Machine` seam (`src/.../machine.py`),
driven in tests by a `FakeMachine` loaded with synthetic fixtures
(`tests/fakes.py`, `tests/fixtures.py`). To exercise one section without the real
machine, run its tests; to check everything, run the full suite:

```sh
uv run pytest tests/test_workspace_collector.py   # one Collector
uv run pytest                                      # full suite (275 passed)
```

A single endpoint against a running instance:

```sh
curl -s http://127.0.0.1:8788/api/flags | jq '.flags | length'
```

## Gotchas

- **Real machine data everywhere.** API JSON, terminal output, and screenshots
  reflect this host (repo paths, git config, installed skills/plugins/MCPs).
  Keep all captured output out of this public, machine-neutral repo.
- **The board self-writes exactly once: a background `git fetch`** against every
  repo under the scan root (default `~/dev`) on load. With many repos or slow
  remotes, `/api/workspace/fetch` keeps streaming for a while before
  `event: done`, so the driver's SSE check accepts frames rather than waiting
  for `done` (13 frames arrived inside the 8s window here).
- **Screenshots need a virtual-time budget.** A plain headless capture catches
  the board mid-fill (fields still read "fetching…"). The driver passes
  `--virtual-time-budget=8000` so ahead/behind and submodule "latest" are filled
  first.
- **Absent things are facts, not failures.** `tsc absent`, Docker "daemon
  unreachable", a repo with "no upstream" all render normally; they are not
  driver errors.
- **Port already in use.** If a board is already on 8787, pass another port
  (the driver took 8788). A busy port makes uvicorn exit and health never
  reaches 200.
- **macOS paths.** Chrome is `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`
  and the Homebrew/Docker collectors are macOS-oriented. On Linux, Chrome is
  `google-chrome`/`chromium` on `PATH` (not verified here).

## Troubleshooting

- **"server never became healthy"** — the port is in use or the app failed to
  import. Re-run on a free port; the driver prints the serve log path
  (`$TMPDIR/wkx-serve.log`), tail it.
- **"screenshot was empty" / Chrome not found** — confirm Google Chrome is
  installed at the path above; the driver's `CHROME` variable is where to
  change it.
- **`/api/workspace/fetch` seems to hang** — it is doing real network fetches,
  bounded by `fetch_workers` / `fetch_timeout` in `config.py`. It is safe to
  interrupt; nothing is written to any working tree.
