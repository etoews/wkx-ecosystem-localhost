"""The RealMachine seam: its safety contract against the real OS.

Faked elsewhere, but its own guarantees, a hard timeout, a missing program
reported not raised, and unreadable paths handled, are what the whole board's
"observer, never operator" posture rests on, so they are pinned here directly.
"""

from __future__ import annotations

from pathlib import Path

from wkx_ecosystem_localhost.machine import (
    NOT_FOUND_RETURNCODE,
    TIMEOUT_RETURNCODE,
    RealMachine,
)


def test_run_captures_a_successful_command() -> None:
    result = RealMachine().run(["echo", "hello"], timeout=5)

    assert result.ok
    assert result.stdout.strip() == "hello"


def test_run_runs_in_the_given_directory(tmp_path: Path) -> None:
    result = RealMachine().run(["pwd"], cwd=tmp_path, timeout=5)

    # macOS symlinks /tmp; compare on the resolved real paths.
    assert Path(result.stdout.strip()).resolve() == tmp_path.resolve()


def test_run_reports_a_timeout_instead_of_hanging() -> None:
    result = RealMachine().run(["sleep", "5"], timeout=0.2)

    assert result.returncode == TIMEOUT_RETURNCODE
    assert not result.ok


def test_run_reports_a_missing_program_instead_of_raising() -> None:
    result = RealMachine().run(["wkx-no-such-program-xyz"], timeout=5)

    assert result.returncode == NOT_FOUND_RETURNCODE


def test_read_file_returns_the_text_of_a_present_file(tmp_path: Path) -> None:
    present = tmp_path / "present.txt"
    present.write_text("contents", encoding="utf-8")

    assert RealMachine().read_file(present) == "contents"


def test_read_file_returns_none_for_a_missing_file(tmp_path: Path) -> None:
    assert RealMachine().read_file(tmp_path / "missing.txt") is None


def test_list_dir_reports_children_and_their_kind(tmp_path: Path) -> None:
    (tmp_path / "child_dir").mkdir()
    (tmp_path / "child_file").write_text("x", encoding="utf-8")

    entries = {entry.name: entry.is_dir for entry in RealMachine().list_dir(tmp_path)}

    assert entries == {"child_dir": True, "child_file": False}


def test_list_dir_is_empty_for_a_missing_path(tmp_path: Path) -> None:
    assert RealMachine().list_dir(tmp_path / "nope") == []
