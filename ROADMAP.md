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
  pinned to release `1.0.0`.

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
| [M8: Token-highlighting](#m8-token-highlighting) | M | ⬜ Deferred |
| [M9: GitHub releases](#m9-github-releases) | M | ⬜ Deferred |
| [M10: Configurable board](#m10-configurable-board) | M | ⬜ Planned |

**Sizes:** S = ≤ a session. M = a focused session or two. L = several sessions.

**Critical path:** M0 → M1 → M2 is sequential. M3, M4, M5 parallelise after M1.
M6 needs the collectors it flags. M7–M9 are opt-in. M10 builds on the Sections
and Flags from M1–M6 and is otherwise independent.

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
- [ ] Tokens are curated: a repo name, a tool name, or a version string. Incidental strings (branches, origins, paths) are not tokens.
- [ ] Two cells match when they share a kind and an identical value: `3.14.4` lights other `3.14.4`, `3.14` does not match `3.14.4`, and there is no semver interpretation. Real divergence is already the drift Flags' job.
- [ ] Hover or keyboard-focus lights the matches; click, Enter, or Space pins the highlight so it survives the pointer leaving; Esc or a click on empty space releases it.
- [ ] Highlighting reaches the whole board, so a value recurring across Sections (a repo in workspace and footprint, a version in toolchains and system) lights up everywhere it appears.
- [ ] The matches take the reserved `--match` colour as a highlighter background, the pinned or hovered one a touch stronger. All other colour stays with the Flag layer, and reduced motion is respected.
- [ ] Tokens are tagged client-side over the rendered cells; no Collector or model changes.

**Hands-on artefact**
- [ ] Hover a version several repos share; every matching cell lights up across panels. Click to pin it, move away, and it stays lit; Esc clears it.
- [ ] `uv run ruff check`, `uv run ty check`, `uv run pytest` all clean.

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
- [ ] Submodule "latest release", token-free: a bounded `curl` through the Machine seam reads the redirect of `https://github.com/<owner>/<repo>/releases/latest` to learn the release tag GitHub blesses. No token, no `SecretStr`, no authenticated API.
- [ ] The tag-based "latest" and the "N behind" count stay as they are, from `git ls-remote`. The GitHub release augments them only when it differs from the highest semver tag, shown labelled so both the tag and the release are legible. Usually they agree; the mismatch is the uncommon case worth surfacing.
- [ ] The release fetch rides the existing submodule SSE probe and degrades gracefully: an unreachable, rate-limited, or release-less repo falls back to the tag-based latest, never an error. Non-GitHub submodules stay tag-based.
- [ ] The tag and the release are distinct model fields (for example `latest_tag` and `github_release`) with clear UI labels; no CONTEXT.md term.
- [ ] Collectors and parsers stay pure over synthetic fixtures in tests (the fake seam returns a canned redirect); no captured machine data.

**Hands-on artefact**
- [ ] A submodule whose GitHub release differs from its highest tag shows both, labelled; one whose release matches shows just the tag.
- [x] Every GitHub repo and submodule carries a working link to its repository; a non-GitHub one carries none.
- [ ] `uv run ruff check`, `uv run ty check`, `uv run pytest` all clean.

---

## M10: Configurable board

Consolidate the configuration that has accreted across earlier milestones (repo
scan roots from M0, the system tools list from M3) into one documented, typed
surface, and add the switches that let an operator shape what the board shows:
which Sections appear, which repos and paths discovery skips, and which Flags are
muted. Configuration stays file-based and read-only from the UI's side, so the
board remains an observer with no auth and no write path.

**Deliverables**
- [ ] Single typed configuration model (extend the existing `pydantic-settings` config), loaded from `.env` and an optional config file, with computed defaults only (never a literal machine path). The real config file is gitignored; a committed example documents the contract with placeholders. Invalid config fails fast with a clear, logged pydantic error.
- [ ] Repo discovery: multiple scan roots, plus per-root include/exclude globs and an ignore list of repos or paths to skip. Folds in the existing single-root default without changing it.
- [ ] Section visibility: turn any Section (workspace, toolchains, claude, system) off. A server-side default in config, plus a client-side view toggle persisted in `localStorage` that mirrors the theme toggle, so hiding a Section needs no server write.
- [ ] Muted Flags: a typed ignore list that drops named Flags (by category, or by item plus category) from the row badges and the Needs attention tally. This is noise suppression, a view preference, never a conformance ruleset. The header still reports "N muted" so nothing is hidden silently.
- [ ] The system tools list (configurable since M3) folded into the consolidated surface and documented alongside the rest.
- [ ] The board never writes server config: all persisted configuration is edited in the file(s). The UI may show what is configured but never mutates it.
- [ ] Config parsing, Section-visibility, and Flag-muting logic covered by unit tests over synthetic fixtures (no captured machine data).

**Hands-on artefact**
- [ ] Point config at a different repo root, or add an ignore glob; the Workspace Section reflects it on reload.
- [ ] Turn a Section off in config and via the client toggle; its panel disappears and comes back.
- [ ] Add a Flag category to the ignore list; its badges vanish, the tally drops by that count, and the header notes "N muted".
- [ ] `uv run ruff check`, `uv run ty check`, `uv run pytest` all clean.
