"""Collector assembly behaviour not covered by the parsers or the HTTP contract.

Chiefly graceful degradation: a probe that exits non-zero leaves that facet
unknown rather than failing the repo, so one wedged command costs a single row's
detail, never the board.
"""

from __future__ import annotations

from fakes import FakeMachine
from fixtures import HOME

from wkx_ecosystem_localhost.collectors.workspace import CONFIG_ARGV, collect_repo
from wkx_ecosystem_localhost.machine import CommandResult

REPO = HOME / "dev" / "silent"


def test_collect_repo_degrades_when_every_probe_fails() -> None:
    # No commands registered: the fake returns a non-zero result for each probe.
    repo = collect_repo(FakeMachine(), REPO, home=HOME)

    assert repo.name == "silent"
    assert repo.path == "~/dev/silent"
    assert repo.branch is None
    assert repo.detached_sha is None
    assert (repo.staged, repo.unstaged, repo.untracked, repo.unmerged) == (0, 0, 0, 0)
    assert repo.stashes == 0
    assert repo.config == []
    assert repo.dirty is False
    assert repo.ahead is None
    assert repo.behind is None


def test_collect_repo_relativises_a_home_path_in_a_config_value() -> None:
    # A whitelisted key (core.editor) whose value carries an absolute home path
    # must not leak the username the relativisation exists to hide.
    config = "global\tcore.editor=/home/dev/tools/edit --wait\n"
    machine = FakeMachine(commands={(REPO, CONFIG_ARGV): CommandResult(0, config, "")})

    repo = collect_repo(machine, REPO, home=HOME)
    editor = next(entry for entry in repo.config if entry.key == "core.editor")

    assert editor.value == "~/dev/tools/edit --wait"
