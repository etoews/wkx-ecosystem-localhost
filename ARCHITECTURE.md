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
no build step. On load the board reads `GET /api/config` for the Off Sections and
`GET /api/view` for the View, removes the panels the operator turned Off in
configuration, and applies the Hidden and Collapsed state and the theme; only then
does it issue one `GET /api/<section>` request for each remaining Section, render
each as stat tiles over sortable tables, and open native `EventSource` streams for
the slow network truths and for View convergence. An Off Section is dropped before
its request fires, so the board never asks for a panel it is about to remove; a
Hidden Section is still fetched and still counts in the tally. The `/` route
stamps the View's theme onto `<html>` as it serves the shell, so the theme never
flashes. Colour is reserved for the Flag layer. Neutral facts are told apart by
weight, a muted tone, and a label, never by hue.

A viewer's preferences live in the View file, not the browser. The View is the
theme, which panels are Hidden or Collapsed, and the Mutes; the board keeps it in
`wkx-ecosystem-localhost.view.toml` beside the configuration, writes it as the
viewer changes the board, and reads it live on every request (ADR 0004). One
client module, `wkxView`, owns this: on load it reads `GET /api/view`, writes each
change through `PATCH /api/view` one preference at a time, and holds
`/api/view/stream` open so a write in one tab converges in every other. The file
holds overrides only, so a fresh board writes nothing and deleting the file resets
the board to its defaults. On the first load after this change `wkxView` migrates
the old `localStorage` keys (`wkx-theme`, `wkx-sections`, `wkx-collapsed`) into the
View and deletes them, so no `localStorage` key remains.

## The service

`app.py` exposes `create_app(settings, machine, home)`, a FastAPI application
factory. Every route reads its configuration from the typed `Settings` and
reaches the host only through the `Machine` seam, which is what lets tests run
the real app end to end on a fake.

| Route | Serves |
| --- | --- |
| `/`, `/static/*` | the board shell and its assets |
| `/api/health` | liveness for the board's own JS and for smoke tests |
| `/api/workspace` | discovered repos with branch, working tree state, stashes, and ROADMAP.md progress for the Roadmap column |
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
| `/api/view` | the effective View; `GET` reads it, `PATCH` writes one preference behind the loopback write guard |
| `/api/view/stream` | SSE, a `view` event on every successful write, so every open tab converges |

A Section named in `sections_off` is not collected and its route is not
registered, so its `/api/<section>` returns 404. `/api/config` and `/api/flags`
are never gated: config is the board's own self-description that the page boots
from, and flags is the cross-cutting layer, not a Section.

The supporting modules are shared by every route: `config.py` (the typed
`Settings`, read from the environment, `.env`, and a TOML file, highest first;
`.env` for secrets, the TOML for everything else; computed, machine-neutral
defaults; the startup scan that rejects an unknown `WKX_ECO_LOCAL_*` variable; and
the read-only effective-config view `/api/config` serves; it reads TOML with
`tomlkit`, the one TOML library the board uses), `view.py` (the View model, the
live drop-and-warn read, and the one-preference merge written atomically under a
process lock and refused when the file on disk does not parse), `models.py` (the
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
It degrades its Section, not the board. `roadmap.py` supports the workspace
Collector: it reads each repo's `ROADMAP.md` through the seam and counts the
task items for the Roadmap column. The read has a 1 MiB cap. A missing file or a
larger file is a plain absence, never a Flag.

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
background `git fetch` per repo, bounded and timed out. This touches
remote-tracking refs only, never a working tree; the board's only other write is
its own View file (ADR 0004). `/api/submodules/probe` lists each submodule's
remote tags to compute latest and releases-behind; no submodule objects are
fetched. `/api/view/stream` is a third SSE stream, but a long-lived one: it stays
open and pushes a `view` event on every successful write, so every tab converges.

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
every Flag, muted or not, because the API is the inventory; the Mute rules are
part of the View, so `/api/view` carries them (they moved out of the
configuration in M12, ADR 0004), and the board drops a muted Flag at one choke
point before it badges a row or counts in the tally. A Muted tile in Needs
attention shows how many the rules silenced, so nothing is hidden silently. This
mirrors Hidden Sections, another view preference: an Off Section is removed on the
server (its route is not registered), but a Hidden Section and a muted Flag both
stay on the wire and are shaped only in the board. The config Section raises two
Flags of its own from the state of the View file: `view-not-saved` (red) when a
write fails, and `view-unknown-key` (amber) when the file names something the
board does not know.

## Redaction

Facts are made safe to display in `redaction.py`, once, before a value reaches
a model: emails are masked, credentials are stripped from remotes, and paths
are relativised to the home directory. No downstream code has to remember to
redact, which is what keeps a casual screenshot of the board from leaking an
identity, a token, or a username.

## Security posture

- Binds to `127.0.0.1` only, with no auth, because loopback plus read-only.
- Every Collector is a probe with a fixed argv and a timeout. The board writes two
  things: the background `git fetch` described above, and its own View file.
- The View file is the one write route. A write is accepted only from loopback and
  the board's own origin: `application/json`, a `Host` that is the bound host and
  port, and a same-origin `Origin` (or none, for a non-browser client); anything
  else is `403`. Each write changes one preference, merges under a lock, and writes
  the file atomically; a file that does not parse stops the write.
- The repo is machine-neutral: no literal paths in code or docs, computed
  configuration defaults, and synthetic fixture data. The View file is gitignored.

## The diagram

[docs/architecture.svg](docs/architecture.svg) is drawn in the `wkx-namespace`
design system and carries both its palettes; it follows the night theme by
default and the day theme when the viewer prefers light.
