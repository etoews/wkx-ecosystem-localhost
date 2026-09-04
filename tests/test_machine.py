"""The RealMachine seam: its safety contract against the real OS.

Faked elsewhere, but its own guarantees, a hard timeout, a missing program
reported not raised, and unreadable paths handled, are what the whole board's
"observer, never operator" posture rests on, so they are pinned here directly.
"""

from __future__ import annotations

from pathlib import Path

from wkx_ecosystem_localhost.machine import (
    CANNOT_EXECUTE_RETURNCODE,
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


def test_run_reports_a_cwd_that_is_a_file_instead_of_raising(tmp_path: Path) -> None:
    # A stale .gitmodules path can name a file as a submodule directory. Running with
    # a file as cwd must be a fact about the probe, never a 500.
    a_file = tmp_path / "a-file"
    a_file.write_text("not a directory", encoding="utf-8")

    result = RealMachine().run(["git", "status"], cwd=a_file, timeout=5)

    assert not result.ok
    assert result.returncode == NOT_FOUND_RETURNCODE
    assert "probe directory missing" in result.stderr


def test_run_reports_a_missing_cwd_instead_of_raising(tmp_path: Path) -> None:
    result = RealMachine().run(["git", "status"], cwd=tmp_path / "gone", timeout=5)

    assert not result.ok
    assert "probe directory missing" in result.stderr


def test_run_reports_a_non_executable_program_instead_of_raising(tmp_path: Path) -> None:
    # A configured tool whose file is present but has no execute bit raises
    # PermissionError from the spawn; it must degrade one row, not the board.
    tool = tmp_path / "not-executable"
    tool.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    tool.chmod(0o644)  # readable, not executable

    result = RealMachine().run([str(tool)], timeout=5)

    assert result.returncode == CANNOT_EXECUTE_RETURNCODE
    assert not result.ok


def test_read_file_returns_the_text_of_a_present_file(tmp_path: Path) -> None:
    present = tmp_path / "present.txt"
    present.write_text("contents", encoding="utf-8")

    assert RealMachine().read_file(present) == "contents"


def test_read_file_returns_none_for_a_missing_file(tmp_path: Path) -> None:
    assert RealMachine().read_file(tmp_path / "missing.txt") is None


def test_read_file_reads_a_file_within_the_byte_cap(tmp_path: Path) -> None:
    within = tmp_path / "within.txt"
    within.write_text("hello", encoding="utf-8")

    # Exactly at the cap is in bounds and read whole, never truncated.
    assert RealMachine().read_file(within, max_bytes=5) == "hello"


def test_read_file_returns_none_for_a_file_over_the_byte_cap(tmp_path: Path) -> None:
    over = tmp_path / "over.txt"
    over.write_text("hello", encoding="utf-8")

    # A file larger than the cap is absent, never a truncated read.
    assert RealMachine().read_file(over, max_bytes=4) is None


def test_read_file_returns_none_for_non_utf8_unbounded(tmp_path: Path) -> None:
    # One latin-1 byte in an include file, .gitmodules, SKILL.md, or package.json
    # must read as unreadable (None), never raise UnicodeDecodeError through the seam.
    latin1 = tmp_path / "latin1.txt"
    latin1.write_bytes(b"caf\xe9")

    assert RealMachine().read_file(latin1) is None


def test_read_file_returns_none_for_non_utf8_within_the_cap(tmp_path: Path) -> None:
    latin1 = tmp_path / "latin1.txt"
    latin1.write_bytes(b"caf\xe9")

    assert RealMachine().read_file(latin1, max_bytes=100) is None


def test_list_dir_reports_children_and_their_kind(tmp_path: Path) -> None:
    (tmp_path / "child_dir").mkdir()
    (tmp_path / "child_file").write_text("x", encoding="utf-8")

    entries = {entry.name: entry.is_dir for entry in RealMachine().list_dir(tmp_path)}

    assert entries == {"child_dir": True, "child_file": False}


def test_list_dir_is_empty_for_a_missing_path(tmp_path: Path) -> None:
    assert RealMachine().list_dir(tmp_path / "nope") == []
