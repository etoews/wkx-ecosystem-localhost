# WKX Ecosystem localhost

A read-only localhost dashboard that inventories this dev machine's ecosystem:
repos, language toolchains, the Claude environment, and system tools. It shows
facts and lights up data-evident anomalies; it never judges the machine against
a written ruleset and never changes it. This glossary is the canonical
ubiquitous language for this context. Where a term has competing synonyms, the
preferred term is defined and the rest are listed under `_Avoid_`.

## Language

### The board and its parts

**WKX Ecosystem localhost**:
The whole thing: the read-only single-page board and the local service behind
it. Named for the repo it lives in. The board is an observer, not an operator.
_Avoid_: the app, the dashboard (as a proper noun)

**Collector**:
A read-only probe that gathers the facts for one part of the board (the
workspace collector, the docker collector, and so on). A collector reports; it
never mutates the machine.
_Avoid_: scanner, agent, monitor

**Section**:
One top-level grouping of the board, addressed by a short label in its panel
heading: workspace, toolchains, claude, system. Distinct from `env` in the
`wkx-namespace` design system: this context has no `env` dimension.

### Provenance of Claude assets

**Origin**:
Where a skill, plugin, or MCP comes from. One of: `user` (authored locally under
`~/.claude`), a `<plugin>@<marketplace>` pair (e.g. `superpowers@claude-plugins-official`),
`project` (a repo-local config), or `built-in`. The one word that answers "where
did this come from" for every Claude asset on the board.
_Avoid_: source (ambiguous with a git remote), provider

### Anomalies

**Flag**:
A data-evident anomaly surfaced as an inline badge on the affected row, derived
purely from the facts a collector already gathered, with no external ruleset. Two
levels: amber (attention) and red (problem). A flag states what the data makes
obvious (dirty tree, behind remote, daemon down); it never measures conformance
to a written standard.
_Avoid_: check, violation, conformance, alert, Status (Status, up/stabilising/down
is the `wkx-platform` operational vocabulary, deliberately not inherited here)
