# WKX Ecosystem localhost

A localhost dashboard that inventories this dev machine's ecosystem: repos,
language toolchains, the Claude environment, and system tools. It shows facts
and lights up data-evident anomalies; it never judges the machine against a
written ruleset, and the one thing it writes is its own View, in a file of its
own. This glossary is the canonical
ubiquitous language for this context. Where a term has competing synonyms, the
preferred term is defined and the rest are listed under `_Avoid_`.

## Language

### The board and its parts

**WKX Ecosystem localhost**:
The whole thing: the single-page board and the local service behind it. Named
for the repo it lives in. The board observes the machine and never operates on
it; the only thing it writes is its own View.
_Avoid_: the app, the dashboard (as a proper noun)

**Collector**:
A read-only probe that gathers the facts for one part of the board (the
workspace collector, the docker collector, and so on). A collector reports; it
never mutates the machine.
_Avoid_: scanner, agent, monitor

**Section**:
One top-level grouping of the board: a panel with its own `signage` heading,
named by a canonical hyphenated id. The ten Sections are workspace,
toolchains, claude, homebrew, system, docker, footprint, editor, git-config,
and config. Needs attention is not a Section; it is the Flag layer's rollup.
Distinct from `env` in the `wkx-namespace` design system: this context has no
`env` dimension.
_Avoid_: panel (the `wkx-namespace` component a Section renders in), tab, card

**Off**:
A Section the operator has removed through configuration. An Off Section is
not collected and not served, so it raises no Flags. Only configuration turns
a Section Off; the board never does.
_Avoid_: disabled (reserved for skills and plugins), excluded, removed

**Hidden**:
A Section, the Needs attention rollup, or a table column the operator has taken
off the board. A Hidden Section is still collected and its Flags still count; a
Hidden column's values are still collected and still reported. Hiding is a
reading preference, not a Mute, and it is part of the View.
_Avoid_: collapsed (the fold-to-heading state, which keeps the Section on the
board), off, dropped, removed

**Collapsed**:
A Section, or the Needs attention rollup, the operator has folded to its
heading. A Collapsed Section stays on the board, is still collected, and its
Flags still count, because collapse is a reading convenience, not a Mute.
Collapsed is part of the View.
_Avoid_: folded, minimised, hidden (the taken-off-the-board state)

**Filter**:
Text the operator gives a Section that keeps only the rows whose visible values
contain it, regardless of letter case, with the matching text marked. A row the
Filter drops is still collected and still reported, and its Flags still count,
because a Filter narrows the reading, not the inventory. A Hidden column is
outside a Filter's reach. The Filter is part of the View.
_Avoid_: search, find, query

**View**:
The operator's arrangement of the board: the theme, which panels are Hidden or
Collapsed, each Section's Filter, each table's sort and Hidden columns, and the
Mutes. The View lives in a file of its own beside the configuration; the board writes it
as the operator changes it and reads it back on load, and the operator does not
need to edit it. Configuration says what the board inventories and how it runs;
the View says how the board reads. A View changes what the board shows, never
what it collects or reports.
_Avoid_: preferences, settings, configuration (the operator's own file), layout,
UI state

**Exclude**:
A glob in configuration that prunes matching directories from repo discovery,
matched against the `~`-relative path the board displays. An excluded repo is
not on the board and raises no Flags; it is absent, not muted.
_Avoid_: ignore, skip list, blacklist

### Provenance of Claude assets

**Origin**:
Where a skill, plugin, or MCP comes from. One of: `user` (authored locally under
`~/.claude`), a `<plugin>@<marketplace>` pair (e.g. `superpowers@claude-plugins-official`),
`project` (a repo-local config), or `built-in`. The one word that answers "where
did this come from" for every Claude asset on the board.
_Avoid_: source (ambiguous with a git remote), provider

### Anomalies

**Flag**:
A data-evident anomaly surfaced as an inline badge on the affected row and rolled
up by category in the board's Needs attention summary, derived purely from the
facts a collector already gathered, with no external ruleset. Two levels: amber
(attention) and red (problem). A flag states what the data makes obvious (dirty
tree, behind remote, daemon down); it never measures conformance to a written
standard.
_Avoid_: check, violation, conformance, alert, Status (Status, up/stabilising/down
is the `wkx-platform` operational vocabulary, deliberately not inherited here)

**Category**:
The kind of a Flag, identified by a stable hyphenated id (`dirty-tree`,
`docker-unreachable`) and shown with a label. The Needs attention summary
rolls Flags up by Category, and a Mute names one.
_Avoid_: type, kind, code, rule

**Mute**:
The operator's instruction, part of the View, to drop a Category, or one item's
Flag within a Category, from the row badges and the Needs attention tally. A
Mute suppresses noise; it never states what the machine should look like, so it
is not a ruleset. The board always reports how many Flags are muted.
_Avoid_: ignore, suppress, silence, whitelist
