# WKX Ecosystem localhost Roadmap

Build order, deliverables, and a hands-on artefact at every milestone for the
localhost board that inventories this dev machine's ecosystem.

The ubiquitous language lives in [CONTEXT.md](CONTEXT.md). The principles below
are the cross-cutting decisions every milestone inherits.

## Principles

- **Inventory, not conformance.** The board shows facts. It never judges the
  machine against a written ruleset.
- **Observer, never operator.** Loopback-bound (`127.0.0.1`), no auth. Every
  Collector is a probe. The board writes two things and nothing else: a
  non-interactive background `git fetch` (bounded, timed out, no working-tree
  effect), and its own View file (M12). It never writes its configuration and
  never changes what it inventories.
- **Machine-neutral repo.** The live UI shows this machine's specifics, but the
  committed code and docs reference nothing machine-specific: inputs come from
  typed config with computed (never literal) defaults, example data is synthetic,
  and the UI relativises paths and redacts remotes by default.
- **`wkx-namespace` for look only.** Palette, typography, theme toggle, panels,
  and fluid grid are borrowed; its `Status` vocabulary and `/wkx/<service>/<env>`
  addressing are not (see [CONTEXT.md](CONTEXT.md), _Flag_).
- **Stack per the standards.** uv, ruff, ty, pytest, stdlib logging,
  pydantic-settings, Typer, `src/` layout. FastAPI + a static HTML/JS frontend;
  htmx unused. The standards ride along as a submodule at `standards/python/`
  pinned to release `1.3.0`.

## Contents

| Milestone | Size | Status |
|-----------|------|--------|
| [M0: Scaffold](#m0-scaffold) | S | ✅ Complete |
| [M1: Workspace slice](#m1-workspace-slice) | M | ✅ Complete |
| [M2: Background fetch + SSE](#m2-background-fetch--sse) | M | ✅ Complete |
| [M3: Toolchains + System tools](#m3-toolchains--system-tools) | M | ✅ Complete |
| [M4: Claude environment](#m4-claude-environment) | M | ✅ Complete |
| [M5: Homebrew + Docker](#m5-homebrew--docker) | S | ✅ Complete |
| [M6: Flag layer](#m6-flag-layer) | M | ✅ Complete |
| [M7: Deferred additions](#m7-deferred-additions) | M | ✅ Complete |
| [M8: Token-highlighting](#m8-token-highlighting) | M | ✅ Complete |
| [M9: GitHub releases](#m9-github-releases) | M | ✅ Complete |
| [M10: Configurable board](#m10-configurable-board) | L | ✅ Complete |
| [M11: Board interaction and refinements](#m11-board-interaction-and-refinements) | M | ✅ Complete |
| [M12: The View lives in its own file](#m12-the-view-lives-in-its-own-file) | L | ⬜ Planned |
| [M13: Table search and hideable columns](#m13-table-search-and-hideable-columns) | M | ⬜ Planned |

**Sizes:** S = ≤ a session. M = a focused session or two. L = several sessions.

**Critical path:** M0 → M1 → M2 is sequential. M3, M4, M5 parallelise after M1.
M6 needs the collectors it flags. M7–M9 are opt-in. M10 builds on the Sections
and Flags from M1–M6 and is otherwise independent. M11 refines the Sections, the
Workspace table, and the Flag layer from M1–M9; it is independent of M10. M12
moves every view preference out of the browser into a View file the board
writes; it is independent of M11. M13 refines every table and depends on M12,
because its controls persist through the View.

---

## M0: Scaffold

**Deliverables**
- [x] `uv init --app`, `src/wkx_ecosystem_localhost/` layout per `standards/python/PROJECT.md`.
- [x] `pyproject.toml` with ruff (`E,F,I,UP,B,SIM,RUF`), ty, pytest; Python 3.14 pin.
- [x] `standards/python/` git submodule (HTTPS URL, pinned to release `1.0.0`, commit `9909b8e`).
- [x] `CLAUDE.md` from the §15 template, with the playbook line rewritten to `./standards/python/PROJECT.md`.
- [x] `config.py` (`pydantic-settings`): repo scan roots (default `Path.home()/"dev"`, never a literal path), port (default `8787`), all machine inputs typed and defaulted by computation. `.env.example` documents the contract with placeholders only.
- [x] `_logging.py` (stdlib) and `exceptions.py` hierarchy.
- [x] `app.py`: FastAPI serving the static board; Typer entry point `wkx-ecosystem-localhost serve` (`--open-browser`) binding uvicorn to `127.0.0.1`.
- [x] `static/`: `index.html` + `styles.css` + `app.js`, vendoring the `wkx-namespace` palette, type stack, theme toggle (`auto/light/dark`, `localStorage`), panel/`signage` components, and fluid grid, with a provenance comment. Masthead "WKX Ecosystem" + "localhost" tag.
- [x] `README.md` noting `git clone --recurse-submodules`.

**Hands-on artefact**
- [x] `uv run wkx-ecosystem-localhost serve` starts on `127.0.0.1:8787`; the page loads with masthead, theme toggle, and empty panels.
- [x] `curl` from another host on the LAN is refused (proves loopback binding).
- [x] `uv run ruff check`, `uv run ty check`, `uv run pytest` all clean.

---

## M1: Workspace slice

The tracer bullet: one Collector wired end-to-end (Collector → pydantic model → JSON API → styled panel) to prove the whole pipeline.

**Deliverables**
- [x] Repo discovery: recurse each configured root, **stop descending at the first `.git`**, skip `node_modules`/`.venv`/hidden, generous safety depth cap.
- [x] Per-repo status via `git status --porcelain=v2 --branch` + `git stash list`: branch (or `detached @ <sha>`), upstream, staged/unstaged/untracked counts, dirty/clean, stash count. **ahead/behind deferred to M2** (shown as "pending").
- [x] Git config: scope-labelled whitelist of safe keys; `user.email` masked by default (raw on demand); credentials stripped from remote URLs; no key material.
- [x] Relativise paths to `~` in the UI.
- [x] `/api/workspace` returns the typed model; the Workspace panel renders it.
- [x] Collectors are pure functions over synthetic fixtures in tests (no captured machine data).

**Hands-on artefact**
- [x] Board shows discovered repos with branch and dirty/clean state.
- [x] A README screenshot uses the synthetic fixture, not real repos.

---

## M2: Background fetch + SSE

**Deliverables**
- [x] Non-interactive background `git fetch` (`GIT_TERMINAL_PROMPT=0`, per-fetch timeout, no submodule recursion, no gc) on a bounded thread pool.
- [x] ahead/behind computed from local refs after fetch, labelled "since last fetch".
- [x] SSE endpoint streams `{repo, ahead, behind}` as each fetch lands; `app.js` fills the fields in via `EventSource` (native, no library).
- [x] Submodules: `git ls-remote --tags <url>` + semver (no `v` prefix required, pre-releases excluded), `git describe --tags` for the pinned version, shown as "pinned · latest · N tags behind".

**Hands-on artefact**
- [x] Open the board; ahead/behind fields fill in progressively.
- [x] This repo's own `standards/python/` submodule reports `pinned 1.0.0`.

---

## M3: Toolchains + System tools

**Deliverables**
- [x] Python: `uv python list`, global pin (`~/.config/uv/.python-version`), per-repo `.python-version`, system `python3`.
- [x] TypeScript/Node: global `tsc`/`node`/`npm` (+ `pnpm`/`bun` if present); per-repo TypeScript from `package.json` and installed `node_modules/typescript`.
- [x] System tools: configurable list with a generic default (`git`, `gh`, `uv`, `ruff`, `ty`, `pre-commit`, `docker`, `terraform`, `aws`, `code`, `node`); present-or-missing + version each.

**Hands-on artefact**
- [x] Toolchains and System panels populate for the real machine.

---

## M4: Claude environment

**Deliverables**
- [x] Skills: user (`~/.claude/skills/`) + plugin skills, each with Origin; all shown, enabled/disabled badged.
- [x] Plugins: from `installed_plugins.json` + `known_marketplaces.json` + `settings.json` enabled state; Origin as marketplace → GitHub repo, plus version. installPaths relativised.
- [x] MCPs: plugin-provided + user/project + built-in, with Origin and auth-needed state (`mcp-needs-auth-cache.json`).
- [x] **Narrow read** of `~/.claude.json`: only `mcpServers` and per-project `mcpServers`; never userID/machineID/oauth/telemetry.

**Hands-on artefact**
- [x] Skills, Plugins, MCPs panels populate with correct Origins.

---

## M5: Homebrew + Docker

**Deliverables**
- [x] Homebrew: `brew outdated` (formulae + casks), list + count.
- [x] Docker: daemon reachable (`docker info`), running/total containers, image count, reclaimable disk (`docker system df`). Read-only.

**Hands-on artefact**
- [x] Homebrew and Docker panels populate; daemon-down renders gracefully.

---

## M6: Flag layer

**Deliverables**
- [x] Per-item flags: dirty tree, detached HEAD, no upstream, behind remote, submodule tags behind, brew outdated, docker down, missing configured tool, MCP auth needed, installed-but-disabled skill/plugin.
- [x] Cross-item flags: tool version drift across repos, `.python-version` drift, skill-name shadowing across Origins, MCP configured in two scopes.
- [x] Inline amber (attention) / red (problem) badges on affected rows, reusing `--chg` / `--del` colours but not the `Status` words.
- [x] Needs attention summary panel with tally tiles (total, attention, problems) and a per-category breakdown. Originally scoped as a single masthead tally; shipped as a panel instead.

**Hands-on artefact**
- [x] Dirty a repo → amber badge appears and the Needs attention tally increments.

---

## M7: Deferred additions

The single bundled roadmap item for the remaining resources: disk footprint,
editor, and the git config inventory. Three new panels under the system
Section; no new Section.

**Deliverables**
- [x] Dev disk footprint: `.venv` and `node_modules` sizes for each discovered repo, per-repo rows plus a total, and Docker disk as total and reclaimable. Sizing via `du` through the Machine seam, synchronous with a cache. The Docker figures reuse the M5 probe, extended to retain the totals it currently discards. No footprint Flags; sizes are facts, thresholds would be a ruleset.
- [x] Editor: VS Code presence and version, plus the installed extensions as a full list with versions, count in the panel heading.
- [x] Git config inventory: the global gitconfig and any config files it points to via include/includeIf, displayed human readably with each key's origin file. Values shown allow-by-default with a targeted redaction pass; secret-bearing families masked, credentials stripped from URL-shaped values, `user.email` unmasked. The divergence from M1's whitelist posture is recorded in an ADR.
- [x] Git config Flags: conflicting config (same key defined more than once across the chain with different values, amber), broken include (red), embedded credentials in a value (red), no identity in the global config (amber).
- [x] Collectors stay pure functions over synthetic fixtures in tests (no captured machine data).

**Hands-on artefact**
- [x] Footprint, Editor, and Git config panels populate for the real machine.
- [x] Add a conflicting key to an included gitconfig file → the amber flag appears and the Needs attention tally increments.
- [x] `uv run ruff check`, `uv run ty check`, `uv run pytest` all clean.

---

## M8: Token-highlighting

The `wkx-namespace` signature interaction, repurposed for the board: hover or
keyboard-focus a recurring value and every other occurrence lights up, so a repo,
a tool, or a version reads across the whole board at a glance. A pure UI
interaction, with no Collector, no new API, and no CONTEXT.md term.

**Deliverables**
- [x] Tokens are curated: a repo name, a tool name, or a version string. Incidental strings (branches, origins, paths) are not tokens.
- [x] Two cells match when they share a kind and an identical value: `3.14.4` lights other `3.14.4`, `3.14` does not match `3.14.4`, and there is no semver interpretation. Real divergence is already the drift Flags' job.
- [x] Hover or keyboard-focus lights the matches; click, Enter, or Space pins the highlight so it survives the pointer leaving; Esc or a click on empty space releases it.
- [x] Highlighting reaches the whole board, so a value recurring across Sections (a repo in workspace and footprint, a version in toolchains and system) lights up everywhere it appears.
- [x] The matches take the reserved `--match` colour as a highlighter background, the pinned or hovered one a touch stronger. All other colour stays with the Flag layer, and reduced motion is respected.
- [x] Tokens are tagged client-side over the rendered cells; no Collector or model changes.

**Hands-on artefact**
- [x] Hover a version several repos share; every matching cell lights up across panels. Click to pin it, move away, and it stays lit; Esc clears it.
- [x] `uv run ruff check`, `uv run ty check`, `uv run pytest` all clean.

---

## M9: GitHub releases

Link every GitHub-hosted item to its repository, and give submodules a more
precise "latest" by reading GitHub's blessed release. A GitHub release is platform
metadata layered on a git tag, so git cannot report it; the board learns the latest
release token-free by following the public `releases/latest` redirect. This is the
board's first outbound non-git network call (see [ADR 0002](docs/adr/0002-github-release-lookup-outbound-http.md)); it stays an observer, the
request is a bounded read.

**Deliverables**
- [x] A clickable link to the GitHub repository on every GitHub-hosted item: each discovered repo and each submodule. The link is derived from the primary remote, and a non-GitHub remote gets none. It exposes only the owner and repo, which M1 already shows credential-stripped, so "redact remotes by default" still holds.
- [x] Submodule "latest release", token-free: a bounded `curl` through the Machine seam reads the redirect of `https://github.com/<owner>/<repo>/releases/latest` to learn the release tag GitHub blesses. No token, no `SecretStr`, no authenticated API.
- [x] The tag-based "latest" and the "N behind" count stay as they are, from `git ls-remote`. The GitHub release augments them only when it differs from the highest semver tag, shown labelled so both the tag and the release are legible. Usually they agree; the mismatch is the uncommon case worth surfacing.
- [x] The release fetch rides the existing submodule SSE probe and degrades gracefully: an unreachable, rate-limited, or release-less repo falls back to the tag-based latest, never an error. Non-GitHub submodules stay tag-based.
- [x] The tag and the release are distinct model fields (`latest` and `github_release`) with clear UI labels; no CONTEXT.md term.
- [x] Collectors and parsers stay pure over synthetic fixtures in tests (the fake seam returns a canned redirect); no captured machine data.

**Hands-on artefact**
- [x] A submodule whose GitHub release differs from its highest tag shows both, labelled; one whose release matches shows just the tag.
- [x] Every GitHub repo and submodule carries a working link to its repository; a non-GitHub one carries none.
- [x] `uv run ruff check`, `uv run ty check`, `uv run pytest` all clean.

---

## M10: Configurable board

Consolidate the configuration that has accreted across earlier milestones (repo
scan roots from M0, the system tools list from M3) into one documented, typed
surface, and add the switches that let an operator shape what the board shows:
which Sections appear, which paths discovery skips, and which Flags are muted.
Configuration is a TOML file; `.env` carries secrets only. The board reads
configuration and shows it, but never writes it, so it remains an observer with
no auth and no write path. The vocabulary (Off, Hidden, Exclude, Category, Mute)
is in [CONTEXT.md](CONTEXT.md).

**Deliverables**
- [x] Configuration file: `wkx-ecosystem-localhost.toml` in the working directory, gitignored, read by the existing `pydantic-settings` model through `TomlConfigSettingsSource`. A committed `wkx-ecosystem-localhost.example.toml` documents every key, commented out, with placeholders. Keys are flat and map one to one onto `Settings` fields; paths accept `~`. A missing file is not an error, because every value has a computed default. The env-only `WKX_ECO_LOCAL_CONFIG_FILE` overrides the path.
- [x] Secrets and configuration split: `.env` holds `SecretStr` values only and stays wired for the first secret; `.env.example` is removed until then. The env prefix becomes `WKX_ECO_LOCAL_`. Precedence, highest first: explicit arguments, environment, `.env`, TOML, defaults. The README documents the split, which diverges from `standards/python/standards/configuration.md` until that standard changes.
- [x] Fail fast: `extra="forbid"` rejects an unknown key in the TOML or `.env`, and a startup scan rejects an unknown `WKX_ECO_LOCAL_*` variable in the environment, which `pydantic-settings` ignores on its own. The error is a clear, logged pydantic error that names the key.
- [x] The TOML joins the `--reload` watch, so a configuration edit restarts the always-on instance the way a code edit does.
- [x] `GET /api/config`: a read-only view of the effective configuration, paths relativised, each value with its source (`default`, `file`, `env`). A `config` Section, last on the board, renders it with tables for excludes, Off Sections, system tools, and mutes. The board never writes configuration.
- [x] Discovery: one global `exclude` list of globs, matched with `PurePath.full_match` against the `~`-relative path of each directory and pruning the walk, so an excluded subtree is never descended. The built-in prunes (hidden directories, `node_modules`, `venv`) stay built-in. No include list and no separate ignore list: an excluded repo is absent, not muted. Discovery caching is its own deliverable below.
- [x] Discovery caching: one board load walks the scan roots once. A `DiscoveryCache` holds the walk behind a TTL (`discovery_cache_ttl`, default 60 seconds), the way the footprint Section holds its `du` result. The cache is built once per app and shared through `app.state` by every route and by the Flag layer, so the several reads that once each re-walked the trees now share one walk. The cache key is the discovery inputs (scan roots, depth, and Excludes), so a changed configuration walks again and is never served a stale result. A fresh app starts with an empty cache.
- [x] Sections: a `Section` enum of the ten Sections in the model, which also types `Flag.section`. `sections_off` names the Off Sections and is validated against the enum. An Off Section is not collected, its route is not registered, and it raises no Flags. Needs attention is not a Section and cannot be Off.
- [x] Client visibility: a `sections` menu in the masthead hides and shows Sections, with the choices in `localStorage` (`wkx-sections`, overrides only) the way the theme toggle keeps its state. A Hidden Section is still collected and its Flags still count. On load the board fetches `/api/config` first, removes Off panels, applies Hidden overrides, then fetches the Sections.
- [x] The `submodule-tags-behind` Flag moves to the `workspace` Section, because submodules are rows of the workspace table and `submodules` is not a Section.
- [x] Muted Flags: `Flag.code` becomes `Flag.category`, and a `CATEGORIES` registry in `flags.py` lists all nineteen, including the two the client raises from SSE. `mute` is a list of `{ category, target? }` rules; an unknown category fails fast; a target matches exactly. The client drops muted Flags at the `wkxFlags.add` choke point, and `/api/flags` still reports every Flag. A Muted tile in Needs attention shows the count, so nothing is hidden silently. This is noise suppression, a view preference, never a conformance ruleset.
- [x] ADR 0003 records that hiding and muting are client-side view preferences and that the API reports every fact. ARCHITECTURE.md's route table, load sequence, and "no external ruleset" line are corrected.
- [x] Config parsing, provenance, the environment scan, discovery excludes, Section Off, and Flag muting are covered by unit tests over synthetic fixtures (no captured machine data). Tests keep constructing `Settings` explicitly and never read a real `.env` or TOML.

**Hands-on artefact**
- [x] Add an `exclude` glob to the TOML and save; the always-on instance restarts, and the Workspace Section drops the matching repos on reload.
- [x] Add `docker` to `sections_off`; the Docker panel and its `docker-unreachable` Flag are gone, and `/api/docker` returns 404. Hide the Editor Section from the `sections` menu and reload; it stays hidden, and its Flags still count.
- [x] Add a mute for `brew-outdated`; its badges vanish, the tally drops by that count, and the Muted tile shows it.
- [x] Set a misspelt `WKX_ECO_LOCAL_PROT`; the server refuses to start with a clear error that names it.
- [x] The config Section shows every effective value with its source.
- [x] `uv run ruff check`, `uv run ty check`, `uv run pytest` all clean.

---

## M11: Board interaction and refinements

Three independent refinements after M10. One is a client-side view preference:
collapse a Section to its heading. Two are not — a Roadmap progress column in
the Workspace Section, backed by one read-only Collector, and a correction to
how the claude Section counts a disabled skill. There is no new Section and no
new route. No refinement writes server config; the collapse choice persists in
`localStorage`, the way the theme toggle does. The vocabulary (Collapsed) is in
[CONTEXT.md](CONTEXT.md). Table search and hideable columns, once part of this
milestone, are [M13](#m13-table-search-and-hideable-columns).

**Deliverables**
- [x] Collapsible Sections: each Section, and the Needs attention rollup, collapses to its `signage` heading and expands again. The whole heading line is the toggle: a button that wraps the label and a rotating caret, the idiom the expandable plugin row already uses, with `aria-expanded` and `aria-controls`. The state lives in `localStorage` (`wkx-collapsed`, a map of panel id to `true`, overrides only, the way `wkx-sections` holds Hidden). Collapse hides the body but keeps the Section on the board; this differs from M10, where the operator turns a Section Off and it disappears. A Collapsed Section is still fetched and still counts in the Needs attention tally, because collapse is a reading convenience, not a Mute. While collapsed, the heading carries a one-line count the Section's render supplies from what it already computes for its tiles, and the Section's own Flag tally (attention and problems, muted excluded); expanded, the tiles carry both. No collapse-all.
- [x] Roadmap progress column: the Workspace Section gets a Roadmap column, to the left of the Flags rail. For a repo with a `ROADMAP.md` at its root (exact name), the column shows ticked against total task items, "42 / 58", with a thin neutral meter beneath and the percentage as the cell's title; it sorts by ratio, empty cells last. A task item is what GitHub Flavored Markdown calls one: a line whose first content is a list marker then `[ ]`, `[x]`, or `[X]`, at any indentation, outside a fenced code block. Nothing else counts, and no heading or table convention is read, so the count works for any repo's file. A file with no task items shows "—", the board's not-applicable glyph, titled "no task items". A repo with no `ROADMAP.md` shows an empty cell, and a submodule row always does, because a pinned checkout's roadmap belongs upstream. The absence is a fact, never a Flag: it is not attention and not a problem, per _Inventory, not conformance_. The cell is not a link and not a token. A `roadmap.py` Collector parses the file through the Machine seam with a pure parser, and `collect_workspace` calls it per repo into a new `Repo.roadmap` field (`ticked` and `total`, or `null`) on the existing `/api/workspace` payload; no new route. The read is bounded: `Machine.read_file` gains an optional `max_bytes`, the Collector caps a `ROADMAP.md` at 1 MiB, and a larger file counts as absent, never as a truncated count.
- [x] Correct the disabled-skill count: a skill's `enabled` becomes the skill's own state, not its plugin's state copied down. Claude Code's `skillOverrides` setting is the source for a user skill: the two user-scope settings files the Collector already reads narrowly for `enabledPlugins` also carry it, and only the `off` tier disables; `name-only` and `user-invocable-only` are visibility tiers the State column shows as facts, never Flags. Per-repo `.claude/settings.local.json` overrides are project-scoped and stay out. A plugin skill has no switch of its own, so it is always enabled on its own; a new `plugin_enabled` field (`null` for a user skill) carries its plugin's state, and the skills table shows a quiet "plugin disabled" note on such a row, with no badge. A disabled plugin already reports as one `plugin-disabled` Flag; its skills must not each add a `skill-disabled` Flag or lift the count, and its MCP servers must not raise `mcp-needs-auth`: a disabled plugin's assets raise no Flags of their own. Only a skill disabled on its own, with its plugin enabled, counts. `skill-disabled` stays in `CATEGORIES`, because a Mute may name it, and now has a real trigger.
- [x] ADR 0003 gains Collapsed beside Hidden as a client-side view preference. ARCHITECTURE.md's list of `localStorage` keys gains `wkx-collapsed`; the README describes collapse, the Roadmap column, and the corrected count.
- [x] The Roadmap parser and Collector, the bounded read, `skillOverrides`, and the corrected Flag derivation are covered by unit tests over synthetic fixtures (no captured machine data). The client-side toggle keeps the `app.js` render smoke-clean, because the test suite does not run it.

**Hands-on artefact**
- [x] Collapse the Workspace Section to its heading and reload; it stays collapsed, and its heading shows the repo count and its Flag tally. Expand it; the repos return. Collapse Needs attention; the tally is unchanged.
- [x] A repo with a `ROADMAP.md` shows its progress in the Roadmap column; a repo with none shows an empty cell and no Flag.
- [x] Disable a plugin that ships skills; the disabled-skill count does not rise, and only the one disabled-plugin Flag appears. Set a user skill to `off` in `skillOverrides`; one `skill-disabled` Flag appears.
- [x] `uv run ruff check`, `uv run ty check`, `uv run pytest` all clean.

---

## M12: The View lives in its own file

Every view preference leaves the browser. The View ([CONTEXT.md](CONTEXT.md):
the theme, which panels are Hidden or Collapsed, and the Mutes; M13 adds the
Filters, sorts, and Hidden columns) moves into `wkx-ecosystem-localhost.view.toml`,
a file beside the configuration that the board owns, writes on every change,
and reads live. The configuration file is untouched: still the operator's,
still read once at startup, still restarted on change. Configuration says what
the board inventories and how it runs; the View says how the board reads. This
is the board's first write route, the reason for
[ADR 0004](docs/adr/0004-the-board-writes-its-view-to-a-file-of-its-own.md),
and the foundation M13 persists through. No Collector and no new Section.

**Deliverables**
- [ ] The View file: `wkx-ecosystem-localhost.view.toml` in the working directory, beside the configuration, gitignored, with a header comment that says the board writes it. `WKX_ECO_LOCAL_VIEW_FILE` overrides the path the way `WKX_ECO_LOCAL_CONFIG_FILE` does. The file holds overrides only: `theme` (`light` or `dark`; absent is `auto`), `sections_hidden` and `sections_collapsed` (panel ids, `summary` for Needs attention), and `[[mute]]` rules. A preference back at its default is removed, so a fresh board writes nothing and the file holds only what the operator changed. The board creates the file on first write and reads it on every request, so a hand edit shows on the next refresh with no restart; the reloader watches the configuration file only, as today.
- [ ] Mute moves into the View. `mute` in the configuration file stops the board at startup with a message that names the View file. The config Section's Mutes table and the Muted tile read the View; `/api/flags` still reports every Flag. The example TOML says where `mute` went.
- [ ] One TOML library: `tomlkit` reads the configuration and reads and writes the View. `tomllib` goes, through a subclass of the pydantic-settings TOML source that overrides only its file read, so the precedence order (argument, environment, `.env`, file, default) is unchanged.
- [ ] Read path: `GET /api/view` returns the effective View; the boot gate fetches it beside `/api/config`. The `/` route stamps `data-theme` onto `<html>` as it serves `index.html`, so the theme never flashes. The config Section gains one line for the View file: its path, and whether it is loaded, absent, or not writable.
- [ ] Write path: `PATCH /api/view` takes one preference per call. The server validates it against the board's own catalogue (panel ids, Categories), merges it under a process-level lock, writes the file atomically (temporary file, then rename), and returns the effective View. When the file on disk does not parse, the write is refused and the board never regenerates the file from memory. A write is accepted only with `Content-Type: application/json`, a `Host` that is the bound host and port, and either a same-origin `Origin` or `Sec-Fetch-Site`, or no `Origin` at all (a non-browser client); anything else is `403`.
- [ ] Every open tab converges: a successful write is pushed as a `view` event on the existing SSE stream, and each tab applies it, so no tab holds a stale View.
- [ ] Two Flags in the config Section, both data-evident: `view-not-saved` (red) when a write fails, and `view-unknown-key` (amber) when the View names a panel, Category, table, or column the board does not know. An unknown View key is dropped with a warning log, never a startup failure, because the board must not refuse to start on a file it wrote itself. The configuration keeps fail-fast.
- [ ] Migration: on the first load after this change, `app.js` reads `wkx-theme`, `wkx-sections`, and `wkx-collapsed` once, writes them through `PATCH /api/view`, and deletes the keys only after the write succeeds. After that no `localStorage` key remains; the tests that pinned those keys now pin their absence.
- [ ] Docs corrected: README (the board writes its View file, and only that), ARCHITECTURE.md (the View file replaces the `localStorage` key list), the example TOML, and `.gitignore`. [ADR 0004](docs/adr/0004-the-board-writes-its-view-to-a-file-of-its-own.md) and the CONTEXT.md entries for View, Filter, Hidden, Collapsed, and Mute are already in.
- [ ] Tests over `tmp_path`, never a real file: the View round trip, overrides-only writing, the parse-failure refusal, the lock, the `403` cases, the `mute`-in-configuration startup message, the drop-and-warn path with its Flag, and the migration order. The client-side code keeps the `app.js` render smoke-clean, because the suite does not run it.

**Hands-on artefact**
- [ ] Switch the theme; `wkx-ecosystem-localhost.view.toml` appears with one line. Open the board in a second browser; it is the same theme.
- [ ] Hide a Section, then edit the View file by hand to show it again and refresh; it is back, with no restart. Edit the configuration file; the board restarts as before.
- [ ] Open two tabs. Hide a Section in one; the other hides it too.
- [ ] `curl -X PATCH` with a foreign `Origin` header is refused with `403`; the same call with no `Origin` succeeds.
- [ ] Make the View file read-only and switch the theme; the config Section raises `view-not-saved`.
- [ ] Put `mute` back in the configuration file; the board stops at startup and says where it went.
- [ ] `uv run ruff check`, `uv run ty check`, `uv run pytest` all clean.

---

## M13: Table search and hideable columns

Three controls that shape how each table reads, on every table of the board:
a Filter per Section, a columns menu per table, and a sort that can be cleared.
Each choice persists through the View file from M12. The design was settled in
a prototype and a design session: the Filter takes the header-native treatment,
the columns menu takes the toolbar treatment, and the vocabulary (Filter, and
Hidden widened to a column) is in [CONTEXT.md](CONTEXT.md). No Collector and no
new Section.

**Deliverables**
- [ ] Filter: each Section's `signage` heading gains a ⌕ button; a click reveals a Filter input beside it, and the input stays visible while a Filter is set, with an "N of M" count. One Filter narrows every table in its Section. A row stays when any of its visible values, the Flag badge text included, contains the Filter text, regardless of letter case; a Hidden column is outside the Filter's reach. The matching text is marked with the M8 token wash (`--match` at 26 %), so the text stays legible in both themes. The Filter runs again when an SSE-raised Flag lands. A filtered-out row is still fetched and its Flags still count. No `/` shortcut.
- [ ] Columns: a slim right-aligned toolbar directly above every table carries a `columns ▾` disclosure, the board's own `.disc` checklist. The name column and the Flags rail are locked and shown as such, so every row stays identifiable and its Flags visible; a table whose columns are all locked still carries the menu, for consistency. Tables that share one column spec (the four Toolchains tables, the two Claude skills tables) share one state, so their columns stay aligned. Column hiding is a class on the table, never a display rule on a cell.
- [ ] Sort gains a third state: a header click goes ascending, descending, then unsorted (source order). The current sort persists per table.
- [ ] A catalogue of table ids and column keys, kebab-case like Section and Category ids (`workspace`, `claude-plugins`, `git-config-keys`, `config-mutes`; `working-tree`, `node-modules`), lives in Python beside the Flag Categories; `PATCH /api/view` validates against it, and a test pins the ids in `app.js` to it the way the Categories are pinned.
- [ ] The View file gains `[filter]` (Section id to text), `[columns_hidden]` (table id to column keys), and `[sort]` (table id to column and direction), overrides only, written through the M12 path with the Filter debounced so typing does not write on every keystroke.
- [ ] The client-side controls keep the `app.js` render smoke-clean, because the test suite does not run it.

**Hands-on artefact**
- [ ] Type in the Workspace Filter; only the matching rows stay, the matches are marked and readable, the count reads "4 of 16", and a click on a header still sorts the narrowed rows.
- [ ] Hide the Stash column; it goes, the View file names it, and it stays hidden after a reload. Show it again; the line leaves the file.
- [ ] Sort by Behind, click twice more; the table is back in source order and the View file has no sort line.
- [ ] Hide a column in one tab; the other tab hides it too.
- [ ] `uv run ruff check`, `uv run ty check`, `uv run pytest` all clean.
