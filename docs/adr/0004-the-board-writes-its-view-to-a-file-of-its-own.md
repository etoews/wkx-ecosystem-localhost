# The board writes its View to a file of its own; the configuration stays the operator's

Until M11 every view preference (theme, Hidden, Collapsed) lived in the browser's
`localStorage`, and the board wrote nothing but a background `git fetch`. From
M12 the View (CONTEXT.md) lives in `wkx-ecosystem-localhost.view.toml`, a TOML
file beside the configuration that the board owns and writes on every change,
reads live on every request, and creates on first use; the operator never needs
to edit it. The configuration file, `wkx-ecosystem-localhost.toml`, is untouched:
still hand-written, still read once at startup, still restarted on change by the
reloader, which does not watch the View file. Mute moves into the View, because
ADR 0003 already classes it as a view preference and only the absence of a write
path had kept it in the configuration. The boundary is one sentence:
configuration says what the board inventories and how it runs; the View says how
the board reads.

We chose two files over the two alternatives. `localStorage` is per browser
profile and is lost with a site-data clear, so a curated set of Mutes or Hidden
columns could vanish; a file survives, reads as text, and copies to the next
machine. One file, with the View as a table inside the configuration, was the
first design and fell to an adversarial review: it makes a file that one person
writes into a file two parties write with no history (the file is gitignored),
so an editor buffer saved over the board's writes, or a board write over a
half-finished hand edit, loses data silently; it also splits one file into live
keys and restart keys, a rule the operator has to remember and the reloader has
to enforce by parsing and diffing every change. With two files, each has one
author and one lifecycle.

Consequences: the board gains a write route, `PATCH /api/view`, one preference
per call, serialised by a process-level lock, written atomically, and refused
when the file on disk does not parse (the board never regenerates it from
memory). A write is accepted only from the board's own origin, or from a
non-browser client, on the bound host. Every open tab learns of a change over
the existing SSE stream. A write that fails, and a View that names a table,
column, Section, or Category the board does not know, each raise a Flag in the
config Section; an unknown View key is dropped with a warning, never a startup
failure, because the board must not refuse to start on a file it wrote itself.
The configuration keeps its fail-fast posture. This supersedes the
`localStorage` half of ADR 0003; its client-side application of Hiding,
Collapsing, and Muting, and its unfiltered API, stand.
