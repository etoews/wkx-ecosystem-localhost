"""A fake ``Machine`` backed by synthetic data.

Structurally satisfies the ``Machine`` protocol. It answers ``list_dir`` from an
in-memory directory set, ``run`` from a table of pre-canned command results, and
``read_file`` from a dict. Loaded entirely from hand-written fixtures, it is what
lets the HTTP tests drive the real app and Collectors without a real machine.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from wkx_ecosystem_localhost.machine import CommandResult, DirEntry


@dataclass
class FakeMachine:
    """An in-memory stand-in for the host machine.

    Attributes:
        dirs: Every directory that exists. ``list_dir`` derives a path's children
            from this set.
        repos: The subset of ``dirs`` that are git repo roots; ``list_dir`` adds a
            synthetic ``.git`` child for each so discovery detects them.
        nondirs: Non-directory entries (files) that exist. ``list_dir`` reports
            them with ``is_dir=False`` so discovery has real files to skip.
        commands: Maps ``(cwd, argv)`` to the result ``run`` returns. An unknown
            command comes back as return code 127, mirroring a missing program.
        files: Maps a path to the text ``read_file`` returns.
    """

    dirs: set[Path] = field(default_factory=set)
    repos: set[Path] = field(default_factory=set)
    nondirs: set[Path] = field(default_factory=set)
    commands: dict[tuple[Path | None, tuple[str, ...]], CommandResult] = field(default_factory=dict)
    files: dict[Path, str] = field(default_factory=dict)

    def run(self, argv: Sequence[str], *, cwd: Path | None = None, timeout: float) -> CommandResult:
        return self.commands.get(
            (cwd, tuple(argv)),
            CommandResult(127, "", "fake: no such command"),
        )

    def read_file(self, path: Path) -> str | None:
        return self.files.get(path)

    def list_dir(self, path: Path) -> list[DirEntry]:
        entries = [DirEntry(child.name, is_dir=True) for child in self.dirs if child.parent == path]
        entries += [DirEntry(f.name, is_dir=False) for f in self.nondirs if f.parent == path]
        if path in self.repos:
            entries.append(DirEntry(".git", is_dir=True))
        return entries
