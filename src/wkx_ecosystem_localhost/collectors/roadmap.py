"""The roadmap Collector: count a repo's task-item progress from its ROADMAP.md.

A read-only refinement of the workspace Section, not a Section of its own. The
pure ``parse_roadmap`` counts GitHub Flavored Markdown task items and nothing
else, so the count works for any repo's file with no heading or table convention
to honour. ``collect_roadmap`` reads ``<repo>/ROADMAP.md`` through the Machine
seam under a size cap, so a missing or oversized file is a plain absence rather
than an error or a truncated count.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from wkx_ecosystem_localhost.machine import Machine
from wkx_ecosystem_localhost.models import RoadmapProgress

logger = logging.getLogger(__name__)

# The exact file name read, at the repo root only. A pinned submodule checkout's
# roadmap belongs upstream, so a submodule is never asked for one.
ROADMAP_FILENAME = "ROADMAP.md"

# The read ceiling. A ROADMAP.md larger than this counts as absent (None), never
# as a truncated count, so a pathological file cannot skew or stall a row.
MAX_ROADMAP_BYTES = 1024 * 1024  # 1 MiB

# One GFM task item: any indentation, then a list marker (unordered ``-``/``*``/
# ``+`` or ordered ``1.``/``1)``), a space, then a ``[ ]``/``[x]``/``[X]`` box
# followed by whitespace or the line end. Nothing else counts.
_TASK_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\[([ xX])\](?:\s|$)")

# A fenced code block delimiter: three or more backticks or tildes, at any
# indentation. Its run character opens and closes the fence so task-like lines
# inside a code sample are never counted.
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")


def parse_roadmap(text: str) -> RoadmapProgress:
    """Count GitHub Flavored Markdown task items in a ROADMAP.md.

    A task item is a line whose first non-space content is a list marker then a
    ``[ ]``, ``[x]``, or ``[X]`` checkbox. Ticked boxes (``x``/``X``) count toward
    ``ticked``; every task item counts toward ``total``. Lines inside a fenced code
    block are skipped, and no heading or table convention is read, so the count
    holds for any file. A file with no task items yields ``total`` 0.

    Args:
        text: The full text of a ROADMAP.md.

    Returns:
        The ticked and total task-item counts.
    """
    ticked = 0
    total = 0
    # The open fence's run character (backtick or tilde), or None outside a fence.
    # A fence closes only on the same character, so a backtick block containing a
    # tilde run stays open.
    fence_char: str | None = None

    for line in text.splitlines():
        fence = _FENCE.match(line)
        if fence:
            run = fence.group(1)
            if fence_char is None:
                fence_char = run[0]
            elif run[0] == fence_char:
                fence_char = None
            continue
        if fence_char is not None:
            continue

        task = _TASK_ITEM.match(line)
        if task:
            total += 1
            if task.group(1) in ("x", "X"):
                ticked += 1

    return RoadmapProgress(ticked=ticked, total=total)


def collect_roadmap(machine: Machine, repo_path: Path) -> RoadmapProgress | None:
    """Read a repo's ROADMAP.md and count its task-item progress.

    Reads ``<repo>/ROADMAP.md`` (that exact name, repo root only) through the
    seam, bounded at 1 MiB. A missing file is a plain absence (None); a file over
    the cap is also absent (None, with a debug log), never a truncated count, so
    the board shows an empty cell rather than an invented figure.

    Args:
        machine: The seam the file is read through.
        repo_path: The repo's root directory.

    Returns:
        The repo's task-item progress, or None when it has no readable, in-bounds
        ROADMAP.md.
    """
    text = machine.read_file(repo_path / ROADMAP_FILENAME, max_bytes=MAX_ROADMAP_BYTES)
    if text is None:
        logger.debug("no readable ROADMAP.md within %d bytes at %s", MAX_ROADMAP_BYTES, repo_path)
        return None
    return parse_roadmap(text)
