# CLAUDE.md

Guidance for Claude Code when working in this repository.

What this is, the build order, and the glossary live in README.md, ROADMAP.md,
and CONTEXT.md. Read CONTEXT.md before naming things: this context has its own
vocabulary (Collector, Origin, Flag, Section) and deliberately does not inherit
the wkx-platform Status vocabulary.

## Agent skills

### Issue tracker

Issues live in this repo's GitHub Issues, via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical roles, each label string equal to its name. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` at the repo root, ADRs in `docs/adr/`. See `docs/agents/domain.md`.

# Python / uv conventions

- All Python work uses uv. Never run bare `pip install`. It will fail anyway (`PIP_REQUIRE_VIRTUALENV=1`).
- Start projects with `uv init <name>` (library) or `uv init --app <name>` (app).
- Add deps with `uv add <pkg>` / `uv add --dev <pkg>`. Remove with `uv remove <pkg>`.
- Run code with `uv run <cmd>` (auto-activates `.venv`). Scripts: `uv run python script.py`.
- After pulling: `uv sync`.
- Per-project Python version: `uv python pin 3.X` (writes `.python-version`). Global default is 3.14.
- Commit: `pyproject.toml`, `uv.lock`, `.python-version`. Gitignore: `.venv/`.
- For global CLI tools (ruff, pre-commit, etc.), use `uv tool install <pkg>`, not `pip install --user`.
- Full playbook: `./standards/python/PROJECT.md` (git submodule pinned to a released tag).
