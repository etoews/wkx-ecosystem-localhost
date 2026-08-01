"""Synthetic, hand-written probe output for the workspace Collector.

Every string here is invented, never captured from a real machine: that is what
keeps the suite runnable anywhere and the public repo machine-neutral. The names
(Ada Lovelace, the analytical-engine repo) are deliberately fictional.

Porcelain v2 reference: ``git status --porcelain=v2 --branch`` emits ``# branch.*``
headers, then ``1``/``2`` (changed), ``u`` (unmerged), ``?`` (untracked) lines.
The two-character ``<XY>`` field is index status (X) then worktree status (Y);
``.`` means unchanged.
"""

from __future__ import annotations

from pathlib import Path

from fakes import FakeMachine

from wkx_ecosystem_localhost.collectors.fetch import AHEAD_BEHIND_ARGV, FETCH_ARGV
from wkx_ecosystem_localhost.collectors.workspace import (
    CONFIG_ARGV,
    STASH_ARGV,
    STATUS_ARGV,
)
from wkx_ecosystem_localhost.machine import CommandResult

# A clean repo tracking an upstream.
STATUS_CLEAN = """\
# branch.oid 1111111111111111111111111111111111111111
# branch.head main
# branch.upstream origin/main
# branch.ab +0 -0
"""

# Staged-only, unstaged-only, and both-at-once, plus two untracked files.
STATUS_DIRTY = """\
# branch.oid 2222222222222222222222222222222222222222
# branch.head feature/login
# branch.upstream origin/feature/login
# branch.ab +2 -1
1 M. N... 100644 100644 100644 aaaa1111 bbbb1111 src/staged_only.py
1 .M N... 100644 100644 100644 cccc2222 dddd2222 src/unstaged_only.py
1 MM N... 100644 100644 100644 eeee3333 ffff3333 src/staged_and_unstaged.py
? untracked_one.py
? untracked_two.py
"""

# Detached HEAD: branch.head is (detached); the short SHA comes from branch.oid.
STATUS_DETACHED = """\
# branch.oid 3333333abc0000000000000000000000000000ff
# branch.head (detached)
1 .M N... 100644 100644 100644 aaaa4444 bbbb4444 work.py
"""

# On a branch that has no upstream yet.
STATUS_NO_UPSTREAM = """\
# branch.oid 4444444444444444444444444444444444444444
# branch.head wip
"""

# A merge conflict (unmerged 'u' line) alongside an untracked file.
STATUS_UNMERGED = """\
# branch.oid 5555555555555555555555555555555555555555
# branch.head main
# branch.upstream origin/main
# branch.ab +0 -0
u UU N... 100644 100644 100644 100644 aaaa5 bbbb5 cccc5 conflict.py
? new.py
"""

# A rename (type '2' entry): staged, with the tab-separated original path.
STATUS_RENAMED = """\
# branch.oid 6666666666666666666666666666666666666666
# branch.head main
2 R. N... 100644 100644 100644 aaaa6666 bbbb6666 R100 new_name.py\told_name.py
"""

# git stash list output: one line per stash.
STASH_EMPTY = ""
STASH_THREE = """\
stash@{0}: WIP on main: 1a2b3c4 wire up the collector
stash@{1}: WIP on feature/login: 5d6e7f8 half-done form
stash@{2}: On main: manual checkpoint
"""

# git config --list --show-scope: <scope>\t<key>=<value> per line.
# Includes secrets (a tokened remote URL, a signing key) that must not survive
# redaction, and non-whitelisted keys that must be dropped entirely.
CONFIG_MIXED = (
    "global\tuser.name=Ada Lovelace\n"
    "global\tuser.email=ada.lovelace@example.com\n"
    "global\tinit.defaultbranch=main\n"
    "global\tcore.editor=code --wait\n"
    "global\tcommit.gpgsign=true\n"
    "global\tgpg.format=ssh\n"
    "global\tuser.signingkey=ABCDEF0123456789ABCDEF\n"
    "local\tremote.origin.url=https://ada:ghp_secrettoken@github.com/ada/analytical-engine.git\n"
    "local\tuser.email=ada@works.example.com\n"
)

# The token that must never survive redaction, for a "no leak" assertion.
SECRET_TOKEN = "ghp_secrettoken"

# git rev-list --left-right --count @{upstream}...HEAD output: "<behind>\t<ahead>".
# web sits 1 behind and 3 ahead of its upstream after the fetch.
AHEAD_BEHIND_WEB = "1\t3\n"

# Synthetic home and scan tree for the HTTP-level tests. All paths are invented.
HOME = Path("/home")
DEV = HOME / "dev"
WEB = DEV / "acme" / "web"
API = DEV / "acme" / "api"


def _ok(stdout: str) -> CommandResult:
    return CommandResult(0, stdout, "")


def build_workspace() -> tuple[FakeMachine, Path, list[Path]]:
    """Build a fake machine, its home, and its scan roots for the API tests.

    Two repos under ``~/dev/acme``: ``web`` is dirty on a tracked branch with a
    stash and a tokened remote (exercising redaction); ``api`` is detached and
    otherwise quiet. Returns the machine plus the home and roots to construct the
    app with.
    """
    machine = FakeMachine(
        dirs={DEV, DEV / "acme", WEB, API},
        repos={WEB, API},
        commands={
            (WEB, STATUS_ARGV): _ok(STATUS_DIRTY),
            (WEB, STASH_ARGV): _ok(STASH_THREE),
            (WEB, CONFIG_ARGV): _ok(CONFIG_MIXED),
            (API, STATUS_ARGV): _ok(STATUS_DETACHED),
            (API, STASH_ARGV): _ok(STASH_EMPTY),
            (API, CONFIG_ARGV): _ok(""),
        },
    )
    return machine, HOME, [DEV]


def build_fetch_workspace() -> tuple[FakeMachine, Path, list[Path]]:
    """Build a fake machine for the SSE background-fetch tests.

    Two repos: ``web`` fetches cleanly and lands 3 ahead / 1 behind its upstream;
    ``api`` cannot reach its remote (no fetch command is registered, so the fake
    returns a non-zero result, standing in for a credential-gated remote) and so
    falls to the unknown state. Returns the machine plus the home and roots to
    construct the app with.
    """
    machine = FakeMachine(
        dirs={DEV, DEV / "acme", WEB, API},
        repos={WEB, API},
        commands={
            (WEB, FETCH_ARGV): _ok(""),
            (WEB, AHEAD_BEHIND_ARGV): _ok(AHEAD_BEHIND_WEB),
        },
    )
    return machine, HOME, [DEV]
