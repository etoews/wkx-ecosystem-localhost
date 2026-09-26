# WKX Ecosystem localhost

[![CI](https://github.com/etoews/wkx-ecosystem-localhost/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/etoews/wkx-ecosystem-localhost/actions/workflows/ci.yml)
[![Python 3.14](https://img.shields.io/badge/python-3.14-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![ty](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ty/main/assets/badge/v0.json)](https://github.com/astral-sh/ty)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://pre-commit.com/)
[![Licence: MIT](https://img.shields.io/badge/licence-MIT-yellow)](LICENSE)

A read-only localhost web app that inventories the dev machine it runs on:
repos and their git status, language toolchains, the Claude environment,
system tools, Homebrew, and Docker. It shows facts, lights up data-evident
anomalies inline, and never changes the machine.

The board is built end to end, from the workspace slice to the flag layer.
[ROADMAP.md](ROADMAP.md) is the build order; [CONTEXT.md](CONTEXT.md) is the
glossary; [ARCHITECTURE.md](ARCHITECTURE.md) is how it is put together.

## The board

Each Section leads with a row of stat tiles and a table beneath. Three controls
shape how a table reads. A Filter keeps only the rows that hold the text and marks
the match; type in the `filter…` pill on a Section heading, and one Filter narrows
every table in the Section. A columns menu above each table hides a column; the
name column and the Flags rail stay. A header click sorts the column up, then
down, then back to source order. The board keeps all three in the View. Click a
Section heading to collapse the Section to its heading. The
collapsed heading shows the Section count and its Flag tally. Click the heading
again to expand the Section. The Section stays on the board while it is collapsed,
so its Flags still count. Press the `g` key (or `/`) to open a jump list. Type to
find a Section. Press `Enter` to go to it.

- **Needs attention**: every open flag rolled up by category, problems first,
  at the top of the board.
- **Workspace**: discovered repos with branch, ahead/behind, working-tree state,
  stashes, and a Roadmap column that shows each repo's `ROADMAP.md` task-item
  progress as "ticked / total" with a thin meter; each submodule nested beneath
  its repo as "pinned · latest · releases-behind".
- **Toolchains**: Python and TypeScript/Node, global and per repo, every subtable
  in one shape (name · version · detail · state) so the columns align.
- **Claude**: plugins with a count of the skills each ships (expand a plugin row
  to reveal them), your own skills in their own table, and MCP servers, each with
  its Origin. Each skill shows its own state. A plugin skill has no switch of its
  own, so it stays enabled; when its plugin is off, the row shows a quiet "plugin
  disabled" note. A skill is disabled only when you set it to `off`.
- **System**: a configurable probe of dev CLIs, present or missing, with versions.
- **Homebrew**: outdated formulae and casks.
- **Docker**: daemon state, containers, images, reclaimable disk.
- **Footprint**: `.venv` and `node_modules` sizes per repo with a total, and
  Docker disk as total and reclaimable.
- **Editor**: VS Code presence and version, with its installed extensions.
- **Git config**: the global gitconfig and the files it includes, each key with
  its origin file, redacted per ADR 0001.
- **Config**: the effective configuration, each value with its source, read only.

Flags are amber (attention) or red (problem), badged on the affected row and
grouped by category in the Needs attention summary; hovering a badge suggests how
to resolve it. No ruleset: a flag states only what the data makes obvious. A
disabled plugin raises one plugin-disabled flag and nothing more for its assets:
its skills and its MCP servers stay quiet. The disabled-skill count is thus the
count of skills you set to `off`, not the skills of a disabled plugin.

## Security posture

- Binds to `127.0.0.1` only, with no auth. Loopback is the boundary, so every
  route — reads included — refuses a request whose `Host` is not a bound loopback
  name and port with `403`, which shuts out a DNS-rebinding page that would
  otherwise reach the board same-origin under its own name.
- Every collector is a probe. The board writes two things and nothing else: a
  non-interactive background `git fetch`, bounded and timed out, which never
  touches a working tree; and its own View file (see below). It never writes its
  configuration and never changes what it inventories.
- The View file is the board's first write route. The board accepts a write only
  from loopback and its own origin: the request must send `application/json`, a
  `Host` that is the bound host and port, and a same-origin `Origin` (or none, for
  a non-browser client). Any other request gets `403`. Each write changes one
  preference, merges under a lock, and writes the file atomically; a corrupt file
  on disk stops the write, because the board never rebuilds the file from memory.
- This repo is machine-neutral: code and docs reference no specific machine,
  config is typed with computed defaults, example data is synthetic, and the
  UI relativises paths and strips credentials from remotes by default.
- The repo's supply chain is gated: the CI workflow token is read-only, each
  action is pinned to a full commit SHA, Dependabot watches the lock file and
  the workflow, and vulnerability alerts and automated security fixes are on.

## Stack

Python 3.14 · uv · FastAPI · pydantic · static HTML/JS frontend with no build
step · SSE for progressive fill-in. Python standards are followed via the
`standards/python/` git submodule, pinned to a released tag of
[python-standards](https://github.com/etoews/python-standards).

The gates beside the tools: a pre-commit hook set (ruff, ty, the lock check,
hygiene checks, a Conventional Commits subject rule, and pytest on push), CI
on every branch that runs that same hook set with each action pinned by
commit, and Dependabot on the lock file and the workflow. See
[Before you commit](#before-you-commit).

The look and feel is borrowed from the `wkx-namespace` design system; its
status vocabulary is deliberately not (see [CONTEXT.md](CONTEXT.md)).

## Running

Clone, sync, and serve:

```sh
git clone --recurse-submodules https://github.com/etoews/wkx-ecosystem-localhost.git
cd wkx-ecosystem-localhost
uv sync
uv run wkx-ecosystem-localhost serve
```

Then open `http://localhost:8787`.

### Options

`serve` takes these options:

| Option | Default | Effect |
| --- | --- | --- |
| `--port <n>` | `8787` | Bind on `127.0.0.1:<n>`. |
| `--open-browser` | off | Open the board in the default browser at startup. |
| `--reload` | off | Restart on a source or configuration change. For development. |

### Configuration

Configuration is a TOML file. `.env` holds secrets only. The board reads its
configuration and shows it in the config Section, but it never writes it.

To change a setting, copy the example file and edit your copy:

```sh
cp wkx-ecosystem-localhost.example.toml wkx-ecosystem-localhost.toml
```

The board reads `wkx-ecosystem-localhost.toml` from the working directory (the
repo root). The file is gitignored, because it names your machine.
`wkx-ecosystem-localhost.example.toml` documents every key with a placeholder and
holds no machine path, so it is safe to commit. Each key is optional. A missing
file, or a missing key, falls back to a value that the board computes at run time,
so the board runs with no configuration at all.

Every key maps one to one onto a setting. A path accepts a leading `~`, which
expands to your home directory. To read the file from another path, set the
environment variable `WKX_ECO_LOCAL_CONFIG_FILE`.

A setting can also come from the environment. A variable is the setting name with
the prefix `WKX_ECO_LOCAL_`, for example `WKX_ECO_LOCAL_PORT`. Precedence, highest
first: an explicit argument, an environment variable, `.env`, the TOML file, then
the computed default.

The board fails fast on a mistake. It refuses to start, with a clear error that
names the key, when the TOML holds an unknown key, when `.env` holds an unknown
prefixed key, or when the environment holds an unknown `WKX_ECO_LOCAL_*` variable
such as a misspelt `WKX_ECO_LOCAL_PROT`.

Secrets are separate. `.env` holds only a secret value (a `SecretStr` field), and
the board stays wired to read `.env` for the first one. There is no secret today,
so no `.env.example` ships until then. This split of configuration from secrets
diverges from `standards/python/standards/configuration.md`, which keeps both in
`.env`; the standard is planned to change to match.

### The View

Configuration is what you set; the View is how you arrange the board. The View is
the theme, which panels are Hidden or Collapsed, each Section's Filter, each
table's Hidden columns and sort, and the Mutes. The board keeps
the View in its own file, `wkx-ecosystem-localhost.view.toml`, beside the
configuration. This is the one file the board writes: it writes the View as you
change the board, and reads it on every request, so a hand edit shows on the next
refresh with no restart. You do not need to edit the file.

To Mute a Flag, hover its badge and select **mute**: the Flag drops from the
badges and the Needs attention tally, and the Muted tile counts it. The
configuration Section's Mutes editor lists every Mute with an **unmute** control,
and adds a Mute for a whole Category a single badge cannot reach. A muted Flag is
suppressed noise, not a resolved one: `GET /api/flags` still reports it.

The View file holds only what you change from the defaults, so a fresh board
writes nothing. Delete the file to reset the board to its defaults. To read it
from another path, set the environment variable `WKX_ECO_LOCAL_VIEW_FILE`, the way
`WKX_ECO_LOCAL_CONFIG_FILE` sets the configuration path. You can symlink the View
file into your dotfiles: the board writes through the link to its target, so the
link is kept and your dotfiles copy stays current.

The board never refuses to start on the View file: a name it does not know is
dropped with a warning and raised as a Flag in the config Section, so the board
always starts on a file it wrote.

### Development

Add `--reload` to restart the server on code changes:

```sh
uv run wkx-ecosystem-localhost serve --reload
```

The reloader watches the package source and the configuration file. A change to
either restarts the server: new code is served, and the new configuration is read
on the restart. Frontend files under `static/` are served from disk, so they are
live on a browser refresh without `--reload`.

To launch and drive the board programmatically, use the
`run-wkx-ecosystem-localhost` skill (`/run`): it starts the app and leaves it
running with its output visible, and its `smoke.sh` driver verifies every
endpoint and screenshots the board. See
[its SKILL.md](.claude/skills/run-wkx-ecosystem-localhost/SKILL.md).

### Before you commit

The repo has a pre-commit gate. `pre-commit` is a dev dependency, so `uv sync`
installs it. Wire the git hooks once per clone:

```sh
uv run pre-commit install
```

That one command wires three stages:

- `pre-commit`, on each commit: `ruff check --fix`, `ruff format`, `ty check`,
  `uv lock --check`, and the hygiene checks (trailing whitespace, end of file,
  YAML, TOML, JSON, large files, merge markers). A hook that changes a file
  refuses the commit. Stage the change and commit again.
- `commit-msg`, on each commit: the first line must be at most 120 characters
  and must start with a Conventional Commits type (`feat`, `fix`, `docs`,
  `test`, `refactor`, `style`, `chore`, `perf`, `build`, `ci`, `revert`), with
  an optional scope and `!`, or with git's own `Revert "`.
- `pre-push`, on each push: `pytest`.

The diagram shows the two sides of the gate. On the laptop, the hooks run on
`git commit` and on `git push`. In GitHub, the CI workflow runs the same hook
set again, and then pytest. A run starts on your `git push` of any branch, on
a Dependabot pull request, or on a rebase-merge in GitHub.

![The CI gates: the hooks on the laptop, and the run in GitHub that repeats them](docs/images/ci.svg)

Like the architecture diagram, [docs/images/ci.svg](docs/images/ci.svg) is drawn in the
`wkx-namespace` design system. It follows the night theme by default and the
day theme when the viewer prefers light.

To run the commit-stage checks on the whole tree:

```sh
uv run pre-commit run --all-files
```

`git commit -n` skips the gate. CI runs the same hook set on every push, so CI
stays the enforcer. `uv run pre-commit autoupdate` bumps the one third-party
hook repo, `pre-commit-hooks`; Dependabot bumps everything else through
`uv.lock`. A Dependabot PR lands without a merge commit: rebase-merge it in
GitHub, or pull it and ff-merge it locally.

`.github/CODEOWNERS` names the owner for every path. GitHub requests the
owner's review on each Dependabot PR, so the owner gets a notification without
watching the repo.

This hook set diverges from `standards/python/standards/pre-commit.md`, which
runs ruff through a mirror and wires one stage.
[python-standards#1](https://github.com/etoews/python-standards/issues/1) is
the planned change to the standard.

### Run at startup (macOS)

You can run the board at login and keep it developable at the same time. A
launchd LaunchAgent runs `serve --reload`, so the one always-on instance is also
the development instance. When you edit the package source, that instance
restarts and serves the new code.

Install it with the helper script:

```sh
uv run scripts/install_launch_on_startup.py
```

The script fills the committed plist template
(`scripts/wkx-ecosystem-localhost.plist.template`) with paths found on your
machine, writes the result to `~/Library/LaunchAgents`, validates it, and loads
the agent. The rendered plist holds machine paths, so it stays out of this
repository. Set `PORT`, `LABEL`, or `UV_BIN` as environment variables to
override the defaults.

Manage the agent (change the label if you set your own):

```sh
# status
launchctl print gui/$(id -u)/dev.$(id -un).wkx-ecosystem-localhost
# restart, for example after a dependency change
launchctl kickstart -k gui/$(id -u)/dev.$(id -un).wkx-ecosystem-localhost
# stop and remove
launchctl bootout gui/$(id -u)/dev.$(id -un).wkx-ecosystem-localhost
```

The reloader watches the package source and the configuration file
(`wkx-ecosystem-localhost.toml`). It picks up a Python code change and a
configuration edit, and reads the new configuration on the restart. It does not
pick up a dependency change (`pyproject.toml` or `uv.lock`), and it does not pick
up a `.env` change on its own. For those, restart the agent with `launchctl
kickstart -k`.

A reload or a stop waits at most 2 seconds for open connections, then closes
them. Each open board tab holds a live View stream that does not end on its own,
so without this limit a reload stops while a tab is open. The tab reconnects its
stream to the new instance automatically.

This pattern has one trade-off. If you save a file with a syntax error or a bad
import, the reloader does not serve the broken code, so the board is down until
you fix it. On a single-user development machine this is the intended behaviour,
because the always-on instance is deliberately the development instance.

## License

Released under the [MIT License](LICENSE).
