"""The single seam between Collectors and the host machine.

Every Collector reaches the machine only through the ``Machine`` interface: run a
fixed-argv command with a timeout, read a file, or list a directory. Collectors
never touch ``subprocess`` or the filesystem directly. Production wires
``RealMachine``; tests wire a fake loaded with synthetic fixtures. Keeping this
the one boundary is what lets the whole suite run on any machine and keeps the
public repo free of captured machine data.
"""

from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# Conventional shell exit codes reused so a Collector can tell a real non-zero
# result from an environment failure without a bespoke error channel.
TIMEOUT_RETURNCODE = 124
NOT_FOUND_RETURNCODE = 127


@dataclass(frozen=True)
class CommandResult:
    """Outcome of a single ``Machine.run`` call.

    A non-zero ``returncode`` is a fact for the Collector to interpret, never an
    exception: a probe that fails leaves its Section degraded, not the board.
    """

    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        """True when the command exited cleanly (return code 0)."""
        return self.returncode == 0


@dataclass(frozen=True)
class DirEntry:
    """One immediate child of a directory: its name and whether it is a directory."""

    name: str
    is_dir: bool


@runtime_checkable
class Machine(Protocol):
    """The read-only surface a Collector is allowed to touch.

    Deliberately narrow. Anything a Collector needs from the host is expressed as
    one of these three primitives so the seam stays testable and auditable.
    """

    def run(self, argv: Sequence[str], *, cwd: Path | None = None, timeout: float) -> CommandResult:
        """Run a fixed argument list, never a shell string, with a hard timeout."""
        ...

    def read_file(self, path: Path, max_bytes: int | None = None) -> str | None:
        """Return the file's text, or None if missing, unreadable, or oversized.

        With ``max_bytes`` set, a file larger than that many bytes returns None
        rather than a truncated read; the default (None) is unbounded, so existing
        callers are unchanged.
        """
        ...

    def list_dir(self, path: Path) -> list[DirEntry]:
        """List a directory's immediate children, or [] if it cannot be read."""
        ...


class RealMachine:
    """The production ``Machine``: subprocess and filesystem, read-only.

    Every command is a fixed argument list (never ``shell=True``), so a
    maliciously named repo or file cannot inject a command, and every call is
    bounded by a timeout so nothing can hang the board. Terminal prompts are
    disabled and optional locks are skipped: probes observe, they never block or
    write.
    """

    def run(self, argv: Sequence[str], *, cwd: Path | None = None, timeout: float) -> CommandResult:
        """Run ``argv`` under a timeout and return its outcome as a fact.

        Args:
            argv: The exact argument list. The first element is the program;
                nothing is interpreted by a shell.
            cwd: Directory to run in, or None for the current one.
            timeout: Hard wall-clock limit in seconds.

        Returns:
            The command's return code and captured output. A timeout or a missing
            program is reported as a non-zero ``CommandResult``, not raised, so a
            single bad probe degrades one row rather than the whole board.
        """
        env = os.environ | {"GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}
        try:
            # argv is always a fixed list; shell=False (the default) so nothing is
            # shell-interpolated and a hostile path or filename cannot inject.
            completed = subprocess.run(
                list(argv),
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                check=False,
            )
        except subprocess.TimeoutExpired:
            logger.warning("probe timed out after %.1fs: %s", timeout, argv[0])
            return CommandResult(TIMEOUT_RETURNCODE, "", f"timed out after {timeout:.1f}s")
        except FileNotFoundError:
            logger.warning("probe program not found: %s", argv[0])
            return CommandResult(NOT_FOUND_RETURNCODE, "", "program not found")
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)

    def read_file(self, path: Path, max_bytes: int | None = None) -> str | None:
        """Return the UTF-8 text of ``path``, or None if it cannot be read.

        With ``max_bytes`` set, at most that many bytes plus one are read: a file
        larger than the cap returns None (never a truncated read), and a file
        within it is decoded whole. A non-UTF-8 payload is treated as unreadable
        (None). The default (None) reads the whole file, unchanged from before.
        """
        try:
            if max_bytes is None:
                return path.read_text(encoding="utf-8")
            with path.open("rb") as handle:
                data = handle.read(max_bytes + 1)
        except OSError:
            return None
        if len(data) > max_bytes:
            return None
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return None

    def list_dir(self, path: Path) -> list[DirEntry]:
        """List the immediate children of ``path``.

        Symlinks are reported as non-directories so discovery never follows one
        into a loop; the depth cap is the backstop. Returns [] if the path is
        missing, not a directory, or unreadable.
        """
        try:
            with os.scandir(path) as it:
                return [DirEntry(e.name, e.is_dir(follow_symlinks=False)) for e in it]
        except OSError:
            return []
