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
| [M7: Deferred additions](#m7-deferred-additions) | M | ⬜ Deferred |
| [M8: Token-highlighting](#m8-token-highlighting) | M | ⬜ Deferred |
| [M9: GitHub Releases API](#m9-github-releases-api) | S | ⬜ Deferred |
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
- [x] Single header tally ("N want attention"). No dedicated flags panel.

**Hands-on artefact**
- [x] Dirty a repo → amber badge appears and the header tally increments.

---

## M7: Deferred additions

The single bundled roadmap item for the remaining resources.

**Deliverables**
- [ ] Dev disk footprint (`.venv`s, `node_modules`, Docker disk).
- [ ] Editor: VS Code + installed extensions.
- [ ] Git config inventory. Display git config in a human readable way and look for conflicting config or misconfig.

---

## M8: Token-highlighting

**Deliverables**
- [ ] The `wkx-namespace` signature interaction repurposed: hover/focus a repo, tool, or version to light up every other occurrence; click to pin; Esc to release.

---

## M9: GitHub Releases API

**Deliverables**
- [ ] Optional precise submodule "latest release" via `/repos/{owner}/{repo}/releases/latest`, for repos where GitHub's release differs from the highest tag.
- [ ] Gated on an optional token (`SecretStr` in config, masked, never committed); tag-based comparison stays the default.

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
