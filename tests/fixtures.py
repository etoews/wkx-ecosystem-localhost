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
from wkx_ecosystem_localhost.collectors.submodules import (
    DESCRIBE_ARGV,
    GITMODULES,
    ls_remote_tags_argv,
)
from wkx_ecosystem_localhost.collectors.toolchains import (
    NODE_VERSION_ARGV,
    NPM_VERSION_ARGV,
    PNPM_VERSION_ARGV,
    PYTHON3_VERSION_ARGV,
    UV_PYTHON_LIST_ARGV,
)
from wkx_ecosystem_localhost.collectors.workspace import (
    CONFIG_ARGV,
    STASH_ARGV,
    STATUS_ARGV,
)
from wkx_ecosystem_localhost.config import ToolSpec
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


# ------------------------- submodule drift fixtures -------------------------
# Two repos with submodules. All tags, paths, and urls are invented.

APP = DEV / "acme" / "app"

# APP's two submodules and their remote urls.
WIDGETS = APP / "libs" / "widgets"
KIT = APP / "tools" / "kit"
WIDGETS_URL = "https://example.com/acme/widgets.git"
KIT_URL = "https://example.com/acme/kit.git"

# API's one submodule, whose remote cannot be reached (no ls-remote registered).
GONE = API / "vendor" / "remote-gone"
GONE_URL = "https://example.com/acme/gone.git"

GITMODULES_APP = (
    '[submodule "libs/widgets"]\n'
    "\tpath = libs/widgets\n"
    f"\turl = {WIDGETS_URL}\n"
    '[submodule "tools/kit"]\n'
    "\tpath = tools/kit\n"
    f"\turl = {KIT_URL}\n"
)
GITMODULES_API = (
    f'[submodule "vendor/remote-gone"]\n\tpath = vendor/remote-gone\n\turl = {GONE_URL}\n'
)

# git ls-remote --tags output: "<sha>\trefs/tags/<tag>", with an annotated tag's
# peeled "^{}" duplicate that must be de-duplicated, a bare (no v) stable ladder,
# and a trailing pre-release that must be excluded while a stable tag exists.
LS_REMOTE_WIDGETS = (
    "1111111111111111111111111111111111111111\trefs/tags/1.0.0\n"
    "2222222222222222222222222222222222222222\trefs/tags/1.2.0\n"
    "3333333333333333333333333333333333333333\trefs/tags/1.3.0\n"
    "4444444444444444444444444444444444444444\trefs/tags/2.0.0\n"
    "4444444444444444444444444444444444444444\trefs/tags/2.0.0^{}\n"
    "5555555555555555555555555555555555555555\trefs/tags/2.1.0-rc.1\n"
)
# A v-prefixed ladder with the pin sitting on the highest tag: latest v3.1.0,
# nothing behind.
LS_REMOTE_KIT = (
    "6666666666666666666666666666666666666666\trefs/tags/v3.0.0\n"
    "7777777777777777777777777777777777777777\trefs/tags/v3.1.0\n"
)


def build_submodule_workspace() -> tuple[FakeMachine, Path, list[Path]]:
    """Build a fake machine whose repos exercise the submodule-drift Collector.

    ``app`` has two submodules: ``libs/widgets`` is pinned at 1.2.0 with two
    stable releases beyond it (latest 2.0.0, two behind, the trailing pre-release
    excluded), and ``tools/kit`` is pinned on the highest v-prefixed tag (latest
    v3.1.0, nothing behind). ``api`` has one submodule whose remote cannot be
    reached, so it lands unknown. Returns the machine plus the home and roots to
    construct the app with.
    """
    machine = FakeMachine(
        dirs={DEV, DEV / "acme", APP, API, WIDGETS, KIT, GONE},
        repos={APP, API},
        files={
            APP / GITMODULES: GITMODULES_APP,
            API / GITMODULES: GITMODULES_API,
        },
        commands={
            (WIDGETS, DESCRIBE_ARGV): _ok("1.2.0\n"),
            (KIT, DESCRIBE_ARGV): _ok("v3.1.0\n"),
            (GONE, DESCRIBE_ARGV): _ok("0.4.0\n"),
            (None, ls_remote_tags_argv(WIDGETS_URL)): _ok(LS_REMOTE_WIDGETS),
            (None, ls_remote_tags_argv(KIT_URL)): _ok(LS_REMOTE_KIT),
        },
    )
    return machine, HOME, [DEV]


# ------------------------- toolchains fixtures -------------------------
# The Python and Node/TypeScript facts. Every version, pin, and manifest is
# invented, never captured from a real machine.

CLI = DEV / "acme" / "cli"

# uv python list output: a download-available line (excluded), the installed
# 3.14.4 listed twice as uv does (a bin symlink and its target, de-duplicated to
# one), an installed 3.13.13, and a download-available pypy (excluded). The
# home-prefixed paths exercise relativisation and the "A -> B" symlink split.
UV_PYTHON_LIST = (
    "cpython-3.15.0a8-macos-aarch64-none    <download available>\n"
    "cpython-3.14.4-macos-aarch64-none      "
    "/home/.local/bin/python3.14 -> "
    "/home/.local/share/uv/python/cpython-3.14-macos-aarch64-none/bin/python3.14\n"
    "cpython-3.14.4-macos-aarch64-none      "
    "/home/.local/share/uv/python/cpython-3.14-macos-aarch64-none/bin/python3.14\n"
    "cpython-3.13.13-macos-aarch64-none     "
    "/home/.local/share/uv/python/cpython-3.13-macos-aarch64-none/bin/python3.13\n"
    "pypy-3.11.11-macos-aarch64-none        <download available>\n"
)

# The uv global pin file and per-repo pins.
UV_GLOBAL_PIN = "3.14.4\n"
WEB_PYTHON_PIN = "3.14.4\n"
API_PYTHON_PIN = "3.13.13\n"

# Per-repo package.json manifests. web declares TypeScript ^5.4.0 but has 5.3.3
# installed (visible drift); api declares ~5.2.0 with nothing installed; cli has
# a manifest but no TypeScript at all, so it drops out of the TypeScript story.
WEB_PACKAGE_JSON = (
    '{\n  "name": "web",\n  "devDependencies": {\n'
    '    "typescript": "^5.4.0",\n    "vite": "^5.0.0"\n  }\n}\n'
)
WEB_INSTALLED_TS = '{\n  "name": "typescript",\n  "version": "5.3.3"\n}\n'
API_PACKAGE_JSON = '{\n  "name": "api",\n  "dependencies": {\n    "typescript": "~5.2.0"\n  }\n}\n'
CLI_PACKAGE_JSON = '{\n  "name": "cli",\n  "dependencies": {\n    "chalk": "^5.3.0"\n  }\n}\n'


def build_toolchains_workspace() -> tuple[FakeMachine, Path, list[Path]]:
    """Build a fake machine exercising the toolchains Collector.

    uv manages two installed interpreters (3.14.4 and 3.13.13) with a download
    line excluded; the uv global pin is 3.14.4. Three repos under ``~/dev/acme``:
    ``web`` pins 3.14.4 and declares TypeScript ^5.4.0 with 5.3.3 installed
    (drift), ``api`` pins 3.13.13 and declares ~5.2.0 with nothing installed, and
    ``cli`` carries a manifest without TypeScript so it drops from the TypeScript
    rows and, lacking a ``.python-version``, from the pins. Globally node and npm
    are present, pnpm is present, and tsc and bun are absent, so an absent tool
    lands as an absent fact. Returns the machine plus the home and roots.
    """
    machine = FakeMachine(
        dirs={DEV, DEV / "acme", WEB, API, CLI},
        repos={WEB, API, CLI},
        files={
            HOME / ".config" / "uv" / ".python-version": UV_GLOBAL_PIN,
            WEB / ".python-version": WEB_PYTHON_PIN,
            WEB / "package.json": WEB_PACKAGE_JSON,
            WEB / "node_modules" / "typescript" / "package.json": WEB_INSTALLED_TS,
            API / ".python-version": API_PYTHON_PIN,
            API / "package.json": API_PACKAGE_JSON,
            CLI / "package.json": CLI_PACKAGE_JSON,
        },
        commands={
            (None, UV_PYTHON_LIST_ARGV): _ok(UV_PYTHON_LIST),
            (None, PYTHON3_VERSION_ARGV): _ok("Python 3.14.5\n"),
            (None, NODE_VERSION_ARGV): _ok("v24.15.0\n"),
            (None, NPM_VERSION_ARGV): _ok("11.12.1\n"),
            (None, PNPM_VERSION_ARGV): _ok("9.1.0\n"),
            # tsc and bun are deliberately unregistered: the fake returns 127,
            # standing in for a tool that is not installed.
        },
    )
    return machine, HOME, [DEV]


# ------------------------- system-tools fixtures -------------------------
# One version banner per tool, each in that tool's own shape, so the parser is
# pinned against every format. Every string is invented, never captured from a
# real machine.

# Labelled: "<name> version <v>".
GIT_VERSION = "git version 2.39.5\n"
# Labelled, then a trailing URL line whose own version must not win.
GH_VERSION = "gh version 2.63.2 (2024-12-05)\nhttps://github.com/cli/cli/releases/tag/v2.63.2\n"
# Name then a bare version with a parenthesised build.
UV_VERSION = "uv 0.5.11 (abc1234 2024-12-05)\n"
# The build hash after the comma must not be read as the version.
DOCKER_VERSION = "Docker version 27.4.0, build bde2b89\n"
# v-prefixed and multi-line: only the first line carries the version.
TERRAFORM_VERSION = "Terraform v1.10.2\non darwin_arm64\n"
# Slash-packed: the CLI version comes before the Python and OS versions.
AWS_VERSION = "aws-cli/2.22.19 Python/3.12.6 Darwin/24.1.0 exe/x86_64\n"
# A bare first-line version followed by a commit hash and an arch line.
CODE_VERSION = "1.96.0\n138f619c86f1199955d53b4166bef66ef252935c\narm64\n"
# The classic bare "v<version>".
NODE_VERSION_OUT = "v22.12.0\n"
# A configuration-added tool probed with a "version" subcommand, not "--version".
WIDGET_VERSION = "widget version 3.2.1\n"

# The configured probe for the tests: the varied real shapes above, one tool
# (ty) deliberately absent, and one (widget) added purely through configuration
# with an overridden version command, so the config-driven probe is exercised.
SYSTEM_TOOLS = [
    ToolSpec(name="git"),
    ToolSpec(name="gh"),
    ToolSpec(name="uv"),
    ToolSpec(name="docker"),
    ToolSpec(name="terraform"),
    ToolSpec(name="aws"),
    ToolSpec(name="code"),
    ToolSpec(name="node"),
    ToolSpec(name="ty"),
    ToolSpec(name="widget", version_args=("version",)),
]


def build_system_workspace() -> tuple[FakeMachine, list[ToolSpec]]:
    """Build a fake machine and its configured tool list for the system Collector.

    Nine tools report a version, each in its own format; ``ty`` is deliberately
    unregistered so the fake returns 127, standing in for a tool that is not
    installed; and ``widget`` is a tool added purely through configuration, probed
    with a ``version`` subcommand rather than ``--version``. Returns the machine
    plus the tool list to build the settings with.
    """
    machine = FakeMachine(
        commands={
            (None, ("git", "--version")): _ok(GIT_VERSION),
            (None, ("gh", "--version")): _ok(GH_VERSION),
            (None, ("uv", "--version")): _ok(UV_VERSION),
            (None, ("docker", "--version")): _ok(DOCKER_VERSION),
            (None, ("terraform", "--version")): _ok(TERRAFORM_VERSION),
            (None, ("aws", "--version")): _ok(AWS_VERSION),
            (None, ("code", "--version")): _ok(CODE_VERSION),
            (None, ("node", "--version")): _ok(NODE_VERSION_OUT),
            (None, ("widget", "version")): _ok(WIDGET_VERSION),
            # ty is deliberately unregistered: the fake returns 127, standing in
            # for a tool that is not installed.
        },
    )
    return machine, SYSTEM_TOOLS


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
