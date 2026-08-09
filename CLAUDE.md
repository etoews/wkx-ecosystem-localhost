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

# Python standards

@standards/python/standards/manifest.md
