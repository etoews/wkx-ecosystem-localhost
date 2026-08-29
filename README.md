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

This pattern has one trade-off. If you save a file with a syntax error or a bad
import, the reloader does not serve the broken code, so the board is down until
you fix it. On a single-user development machine this is the intended behaviour,
because the always-on instance is deliberately the development instance.

## License

Released under the [MIT License](LICENSE).
