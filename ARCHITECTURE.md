# Architecture

WKX Ecosystem localhost is a single service and a single page. The service
inventories the machine through read-only probes and serialises what it finds;
the page renders those facts and never asks for anything but JSON. Requests
flow down through one narrow seam, facts flow back up as typed models, and
colour appears only when the data raises a Flag.

The vocabulary used here (Collector, Section, Origin, Flag) is defined in
[CONTEXT.md](CONTEXT.md).

![Simplified architecture, five layers from the board down to the dev machine](docs/architecture.svg)

## The board

`src/wkx_ecosystem_localhost/static/` is the whole frontend: `index.html` (the
shell), `styles.css` (the wkx-namespace look and feel), and `app.js`. There is
no build step. On load the board first fetches `GET /api/config`, removes the
panels the operator turned Off in configuration, and applies the viewer's Hidden
overrides from the `sections` menu; only then does it issue one
`GET /api/<section>` request for each remaining Section, render each as stat
tiles over sortable tables, and open two native `EventSource` streams for the
slow network truths. An Off Section is dropped before its request fires, so the
board never asks for a panel it is about to remove; a Hidden Section is still
fetched and still counts in the tally. Colour is reserved for the Flag layer.
Neutral facts are told apart by weight, a muted tone, and a label, never by hue.

A viewer's preferences live in the browser's `localStorage` and nowhere else:
`wkx-theme` (light or dark; an absent key means auto), `wkx-sections` (the Hidden
overrides; an absent key means the server default), and `wkx-collapsed` (the
Collapsed panels; an absent key means every panel is expanded). Each key holds
overrides only, so a cleared store returns the board to its defaults, and no
preference ever reaches the service.

## The service

`app.py` exposes `create_app(settings, machine, home)`, a FastAPI application
factory. Every route reads its configuration from the typed `Settings` and
reaches the host only through the `Machine` seam, which is what lets tests run
the real app end to end on a fake.

| Route | Serves |
| --- | --- |
| `/`, `/static/*` | the board shell and its assets |
| `/api/health` | liveness for the board's own JS and for smoke tests |
| `/api/workspace` | discovered repos with branch, working tree state, and stashes |
| `/api/workspace/fetch` | SSE, each repo's ahead/behind as its background fetch lands |
| `/api/submodules` | each repo's submodules with pins resolved |
| `/api/submodules/probe` | SSE, each submodule's latest release and tags-behind |
| `/api/toolchains` | Python and TypeScript/Node, global and per repo |
| `/api/claude` | skills, plugins, and MCP servers, each with its Origin |
| `/api/system` | configured dev CLIs, present with version or missing |
| `/api/homebrew` | outdated formulae and casks, or Homebrew's absence |
| `/api/docker` | daemon reachability, container and image counts, total and reclaimable disk |
| `/api/git-config` | the global gitconfig chain: keys, includes, and identity, redacted per ADR 0001 |
| `/api/editor` | VS Code presence and version, with its installed extensions |
| `/api/footprint` | per-repo `.venv` and `node_modules` disk sizes alongside the Docker disk, cached |
| `/api/flags` | open Flags, each naming the Section and row it badges |
| `/api/config` | the effective configuration, each value tagged with its source, read only |

A Section named in `sections_off` is not collected and its route is not
registered, so its `/api/<section>` returns 404. `/api/config` and `/api/flags`
are never gated: config is the board's own self-description that the page boots
from, and flags is the cross-cutting layer, not a Section.

The supporting modules are shared by every route: `config.py` (the typed
`Settings`, read from the environment, `.env`, and a TOML file, highest first;
`.env` for secrets, the TOML for everything else; computed, machine-neutral
defaults; the startup scan that rejects an unknown `WKX_ECO_LOCAL_*` variable; and
the read-only effective-config view `/api/config` serves), `models.py` (the
Section models the API serialises verbatim, and the `Section` enum that types
`Flag.section` and `sections_off`), `sse.py` (SSE framing for
`EventSource`), `cache.py` (the one-slot TTL cache behind the footprint Section
and behind repo discovery, so one board load walks the scan roots once no matter
how many routes and the Flag layer ask for the repos), `redaction.py`,
`semver.py`, `_logging.py`, and `exceptions.py`.

`__main__.py` is the typer entry point. `serve` builds `Settings` once, binds
uvicorn to `127.0.0.1:8787`, and opens the board in a browser. The bind host is
deliberately not a setting; loopback-only is a security property of the app.

## Collectors

Each file in `collectors/` is a Collector: a pure function from `Machine` probe
results to a typed model, one per Section plus `fetch.py` for the streamed
counts. A Collector never touches subprocess or the filesystem directly, and a
probe that fails is a fact for the Collector to interpret, never an exception.
It degrades its Section, not the board.

## The Machine seam

`machine.py` is the one boundary between the app and the host. The `Machine`
protocol is deliberately narrow, three primitives only: `run(argv, timeout)`,
`read_file`, and `list_dir`. Production wires `RealMachine` (subprocess and the
filesystem); tests wire a `FakeMachine` loaded with synthetic fixtures and
drive the real app through it. Keeping this the only boundary is what lets the
whole suite run on any machine and keeps the public repo free of captured
machine data.

## Progressive fill-in over SSE

Two truths need the network and would otherwise stall the board, so both
arrive over Server-Sent Events on a bounded worker pool, each result pushed
the moment it is ready. `/api/workspace/fetch` runs a non-interactive
background `git fetch` per repo, bounded and timed out. This is the one write
the app performs anywhere, and it touches remote-tracking refs only, never a
working tree. `/api/submodules/probe` lists each submodule's remote tags to
compute latest and releases-behind; no submodule objects are fetched.

## Flags

`flags.py` is the cross-cutting Flag layer, not a panel. It reruns the
Collectors whose facts a Flag can be derived from and returns the open Flags,
each naming the Category and row it badges, amber for attention and red for a
problem. A Flag states only what the data makes obvious. The only configuration
that touches a Flag is a Mute, which suppresses noise; it is a view preference,
not a ruleset, because it never states what the machine must look like. Flags
that need the network to be known (behind remote, releases-behind) are raised by
the board itself as the SSE events land.

Muting is applied in the client, not the server (ADR 0003). `/api/flags` reports
every Flag, muted or not, because the API is the inventory; `/api/config` carries
the Mute rules, and the board drops a muted Flag at one choke point before it
badges a row or counts in the tally. A Muted tile in Needs attention shows how
many the rules silenced, so nothing is hidden silently. This mirrors Hidden
Sections, another client-side view preference: an Off Section is removed on the
server (its route is not registered), but a Hidden Section and a muted Flag both
stay on the wire and are shaped only in the board.

## Redaction

Facts are made safe to display in `redaction.py`, once, before a value reaches
a model: emails are masked, credentials are stripped from remotes, and paths
are relativised to the home directory. No downstream code has to remember to
redact, which is what keeps a casual screenshot of the board from leaking an
identity, a token, or a username.

## Security posture

- Binds to `127.0.0.1` only, with no auth, because loopback plus read-only.
- Every Collector is a probe with a fixed argv and a timeout; the one write is
  the background `git fetch` described above.
- The repo is machine-neutral: no literal paths in code or docs, computed
  configuration defaults, and synthetic fixture data.

## The diagram

[docs/architecture.svg](docs/architecture.svg) is drawn in the `wkx-namespace`
design system and carries both its palettes; it follows the night theme by
default and the day theme when the viewer prefers light.
