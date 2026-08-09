# WKX Ecosystem localhost

A read-only localhost web app that inventories the dev machine it runs on:
repos and their git status, language toolchains, the Claude environment,
system tools, Homebrew, and Docker. It shows facts, lights up data-evident
anomalies inline, and never changes the machine.

The board is built end to end, from the workspace slice to the flag layer.
[ROADMAP.md](ROADMAP.md) is the build order; [CONTEXT.md](CONTEXT.md) is the
glossary; [ARCHITECTURE.md](ARCHITECTURE.md) is how it is put together.

## The board

Each Section leads with a row of stat tiles and a table beneath; every table sorts
on any column.

- **Needs attention**: every open flag rolled up by category, problems first,
  at the top of the board.
- **Workspace**: discovered repos with branch, ahead/behind, working-tree state
  and stashes, each submodule nested beneath its repo as "pinned · latest ·
  releases-behind".
- **Toolchains**: Python and TypeScript/Node, global and per repo, every subtable
  in one shape (name · version · detail · state) so the columns align.
- **Claude**: plugins with a count of the skills each ships (expand a plugin row
  to reveal them), your own skills in their own table, and MCP servers, each with
  its Origin.
- **System**: a configurable probe of dev CLIs, present or missing, with versions.
- **Homebrew**: outdated formulae and casks.
- **Docker**: daemon state, containers, images, reclaimable disk.

Flags are amber (attention) or red (problem), badged on the affected row and
grouped by category in the Needs attention summary; hovering a badge suggests how
to resolve it. No ruleset: a flag states only what the data makes obvious.

## Security posture

- Binds to `127.0.0.1` only; no auth, because loopback plus read-only.
- Every collector is a probe. The one write allowed anywhere is a
  non-interactive background `git fetch`, bounded and timed out, which never
  touches a working tree.
- This repo is machine-neutral: code and docs reference no specific machine,
  config is typed with computed defaults, example data is synthetic, and the
  UI relativises paths and strips credentials from remotes by default.

## Stack

Python 3.14 · uv · FastAPI · pydantic · static HTML/JS frontend with no build
step · SSE for progressive fill-in. Python standards are followed via the
`standards/python/` git submodule, pinned to a released tag of
[python-standards](https://github.com/etoews/python-standards).

The look and feel is borrowed from the `wkx-namespace` design system; its
status vocabulary is deliberately not (see [CONTEXT.md](CONTEXT.md)).

## Running

```sh
git clone --recurse-submodules https://github.com/etoews/wkx-ecosystem-localhost.git
cd wkx-ecosystem-localhost
uv sync
uv run wkx-ecosystem-localhost serve
```

Then open `http://127.0.0.1:8787`. Pass `--port <n>` to bind elsewhere or
`--open-browser` to open it automatically.

While developing, add `--reload` to restart the server on code changes:

```sh
uv run wkx-ecosystem-localhost serve --reload
```

This is for development only, not the always-on service. It re-reads
configuration on each restart, so config changes are picked up too. Frontend
files under `static/` are served from disk and are already live on a browser
refresh without it.

To launch and drive the board programmatically, use the
`run-wkx-ecosystem-localhost` skill (`/run`): it starts the app and leaves it
running with its output visible, and its `smoke.sh` driver verifies every
endpoint and screenshots the board. See
[its SKILL.md](.claude/skills/run-wkx-ecosystem-localhost/SKILL.md).

## License

Released under the [MIT License](LICENSE).
