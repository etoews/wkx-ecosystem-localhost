# WKX Ecosystem localhost Roadmap

Build order, deliverables, and a hands-on artefact at every milestone for the
read-only localhost board that inventories this dev machine's ecosystem.

The ubiquitous language lives in [CONTEXT.md](CONTEXT.md). The principles below
are the cross-cutting decisions every milestone inherits.

## Principles

- **Inventory, not conformance.** The board shows facts. It never judges the
  machine against a written ruleset.
- **Observer, never operator.** Loopback-bound (`127.0.0.1`), read-only, no auth.
  Every Collector is a probe; the one write we allow is a non-interactive
  background `git fetch` (bounded, timed out, no working-tree effect).
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
| [M11: Board interaction and refinements](#m11-board-interaction-and-refinements) | M | ⬜ Planned |
| [M12: Table search and hideable columns](#m12-table-search-and-hideable-columns) | M | ⬜ Planned |

**Sizes:** S = ≤ a session. M = a focused session or two. L = several sessions.

**Critical path:** M0 → M1 → M2 is sequential. M3, M4, M5 parallelise after M1.
M6 needs the collectors it flags. M7–M9 are opt-in. M10 builds on the Sections
and Flags from M1–M6 and is otherwise independent. M11 refines the Sections, the
Workspace table, and the Flag layer from M1–M9; it is independent of M10. M12
refines every table; it is independent of M11 and can follow it or run beside it.

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
milestone, are [M12](#m12-table-search-and-hideable-columns).

**Deliverables**
- [ ] Collapsible Sections: each Section, and the Needs attention rollup, collapses to its `signage` heading and expands again. The whole heading line is the toggle: a button that wraps the label and a rotating caret, the idiom the expandable plugin row already uses, with `aria-expanded` and `aria-controls`. The state lives in `localStorage` (`wkx-collapsed`, a map of panel id to `true`, overrides only, the way `wkx-sections` holds Hidden). Collapse hides the body but keeps the Section on the board; this differs from M10, where the operator turns a Section Off and it disappears. A Collapsed Section is still fetched and still counts in the Needs attention tally, because collapse is a reading convenience, not a Mute. While collapsed, the heading carries a one-line count the Section's render supplies from what it already computes for its tiles, and the Section's own Flag tally (attention and problems, muted excluded); expanded, the tiles carry both. No collapse-all.
- [x] Roadmap progress column: the Workspace Section gets a Roadmap column, to the left of the Flags rail. For a repo with a `ROADMAP.md` at its root (exact name), the column shows ticked against total task items, "42 / 58", with a thin neutral meter beneath and the percentage as the cell's title; it sorts by ratio, empty cells last. A task item is what GitHub Flavored Markdown calls one: a line whose first content is a list marker then `[ ]`, `[x]`, or `[X]`, at any indentation, outside a fenced code block. Nothing else counts, and no heading or table convention is read, so the count works for any repo's file. A file with no task items shows "—", the board's not-applicable glyph, titled "no task items". A repo with no `ROADMAP.md` shows an empty cell, and a submodule row always does, because a pinned checkout's roadmap belongs upstream. The absence is a fact, never a Flag: it is not attention and not a problem, per _Inventory, not conformance_. The cell is not a link and not a token. A `roadmap.py` Collector parses the file through the Machine seam with a pure parser, and `collect_workspace` calls it per repo into a new `Repo.roadmap` field (`ticked` and `total`, or `null`) on the existing `/api/workspace` payload; no new route. The read is bounded: `Machine.read_file` gains an optional `max_bytes`, the Collector caps a `ROADMAP.md` at 1 MiB, and a larger file counts as absent, never as a truncated count.
- [x] Correct the disabled-skill count: a skill's `enabled` becomes the skill's own state, not its plugin's state copied down. Claude Code's `skillOverrides` setting is the source for a user skill: the two user-scope settings files the Collector already reads narrowly for `enabledPlugins` also carry it, and only the `off` tier disables; `name-only` and `user-invocable-only` are visibility tiers the State column shows as facts, never Flags. Per-repo `.claude/settings.local.json` overrides are project-scoped and stay out. A plugin skill has no switch of its own, so it is always enabled on its own; a new `plugin_enabled` field (`null` for a user skill) carries its plugin's state, and the skills table shows a quiet "plugin disabled" note on such a row, with no badge. A disabled plugin already reports as one `plugin-disabled` Flag; its skills must not each add a `skill-disabled` Flag or lift the count, and its MCP servers must not raise `mcp-needs-auth`: a disabled plugin's assets raise no Flags of their own. Only a skill disabled on its own, with its plugin enabled, counts. `skill-disabled` stays in `CATEGORIES`, because a Mute may name it, and now has a real trigger.
- [ ] ADR 0003 gains Collapsed beside Hidden as a client-side view preference. ARCHITECTURE.md's list of `localStorage` keys gains `wkx-collapsed`; the README describes collapse, the Roadmap column, and the corrected count.
- [ ] The Roadmap parser and Collector, the bounded read, `skillOverrides`, and the corrected Flag derivation are covered by unit tests over synthetic fixtures (no captured machine data). The client-side toggle keeps the `app.js` render smoke-clean, because the test suite does not run it.

**Hands-on artefact**
- [ ] Collapse the Workspace Section to its heading and reload; it stays collapsed, and its heading shows the repo count and its Flag tally. Expand it; the repos return. Collapse Needs attention; the tally is unchanged.
- [ ] A repo with a `ROADMAP.md` shows its progress in the Roadmap column; a repo with none shows an empty cell and no Flag.
- [ ] Disable a plugin that ships skills; the disabled-skill count does not rise, and only the one disabled-plugin Flag appears. Set a user skill to `off` in `skillOverrides`; one `skill-disabled` Flag appears.
- [ ] `uv run ruff check`, `uv run ty check`, `uv run pytest` all clean.

---

## M12: Table search and hideable columns

Two client-side view preferences that shape how each table reads, moved out of
M11 so that milestone stays small: search and filter a table, and hide a column.
No Collector, no API change, no new Section. The choices that persist live in
`localStorage`, the way the theme toggle does. The open design questions (which
tables carry the controls, the matching semantics, whether a search persists,
the control for columns, and whether Hidden generalises from a Section to a
column in [CONTEXT.md](CONTEXT.md)) are settled in this milestone's own design
session.

**Deliverables**
- [ ] Table search and filter: the board's tables get a consistent search-and-filter control, next to the click-to-sort they already carry. A search box keeps only the rows that match its text, and sort still works on the narrowed rows. This helps the long tables — Workspace, Toolchains, Footprint. The control is client-side, with no Collector and no API change.
- [ ] Hideable columns: each table's columns can be hidden and shown again, with each choice held client-side in `localStorage`. The operator drops the columns they do not need, such as Stash or Upstream. The name column and the Flags rail always stay, so every row is identifiable and its Flags stay visible.
- [ ] The client-side controls keep the `app.js` render smoke-clean, because the test suite does not run it.

**Hands-on artefact**
- [ ] Type in a table's search box; only the matching rows stay, and a click on a header still sorts them.
- [ ] Hide a column; it goes and the choice survives a reload. Show it again; it returns.
- [ ] `uv run ruff check`, `uv run ty check`, `uv run pytest` all clean.
