"""``collect_roadmap`` assembly: the exact-name, root-only, bounded read.

Drives the Collector over a fake seam loaded with synthetic ROADMAP.md text, so
the missing-file absence, the size cap, and the exact-name-at-root rule are all
pinned without touching a real filesystem.
"""

from __future__ import annotations

from pathlib import Path

from fakes import FakeMachine

from wkx_ecosystem_localhost.collectors.roadmap import (
    MAX_ROADMAP_BYTES,
    ROADMAP_FILENAME,
    collect_roadmap,
)

REPO = Path("/home/dev/acme/web")

ROADMAP_TEXT = "# Roadmap\n- [x] done\n- [ ] open\n- [ ] also open\n"


def test_a_present_roadmap_is_parsed_into_progress() -> None:
    machine = FakeMachine(files={REPO / ROADMAP_FILENAME: ROADMAP_TEXT})

    progress = collect_roadmap(machine, REPO)

    assert progress is not None
    assert (progress.ticked, progress.total) == (1, 3)


def test_a_missing_roadmap_is_absent() -> None:
    # No file registered: the seam reports the path missing.
    assert collect_roadmap(FakeMachine(), REPO) is None


def test_a_roadmap_over_the_cap_is_absent_never_truncated() -> None:
    # One ticked task followed by filler that pushes the file past 1 MiB. A
    # truncated read would still count the task; an over-cap read must be absent.
    oversized = "- [x] one real task\n" + ("x" * (MAX_ROADMAP_BYTES + 1))
    machine = FakeMachine(files={REPO / ROADMAP_FILENAME: oversized})

    assert collect_roadmap(machine, REPO) is None


def test_a_roadmap_at_exactly_the_cap_is_still_read() -> None:
    # A file whose byte length is exactly the cap is in bounds and read.
    body = "- [x] task\n"
    padded = body + ("x" * (MAX_ROADMAP_BYTES - len(body.encode("utf-8"))))
    machine = FakeMachine(files={REPO / ROADMAP_FILENAME: padded})

    progress = collect_roadmap(machine, REPO)

    assert progress is not None
    assert (progress.ticked, progress.total) == (1, 1)


def test_only_the_exact_root_filename_is_read() -> None:
    # A wrong-case name and a nested copy both exist; neither is the file read.
    machine = FakeMachine(
        files={
            REPO / "roadmap.md": ROADMAP_TEXT,
            REPO / "docs" / ROADMAP_FILENAME: ROADMAP_TEXT,
        }
    )

    assert collect_roadmap(machine, REPO) is None


def test_a_roadmap_with_no_task_items_reports_zero_total() -> None:
    machine = FakeMachine(files={REPO / ROADMAP_FILENAME: "# Roadmap\n\nJust prose.\n"})

    progress = collect_roadmap(machine, REPO)

    assert progress is not None
    assert (progress.ticked, progress.total) == (0, 0)
