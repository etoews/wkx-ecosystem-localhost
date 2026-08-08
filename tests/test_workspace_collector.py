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


def test_collect_repo_derives_the_github_link_from_the_origin_remote() -> None:
    config = "local\tremote.origin.url=git@github.com:ada/analytical-engine.git\n"
    machine = FakeMachine(commands={(REPO, CONFIG_ARGV): CommandResult(0, config, "")})

    repo = collect_repo(machine, REPO, home=HOME)

    assert repo.github == "https://github.com/ada/analytical-engine"


def test_collect_repo_leaves_a_non_github_remote_unlinked() -> None:
    config = "local\tremote.origin.url=https://gitlab.com/ada/engine.git\n"
    machine = FakeMachine(commands={(REPO, CONFIG_ARGV): CommandResult(0, config, "")})

    repo = collect_repo(machine, REPO, home=HOME)

    assert repo.github is None


def test_collect_repo_has_no_github_link_without_a_remote() -> None:
    # No config command registered: the fake returns non-zero, so config is empty
    # and there is no remote to derive a link from.
    repo = collect_repo(FakeMachine(), REPO, home=HOME)

    assert repo.github is None


def test_collect_repo_prefers_origin_over_another_remote_for_the_link() -> None:
    config = (
        "local\tremote.upstream.url=https://gitlab.com/ada/fork.git\n"
        "local\tremote.origin.url=https://github.com/ada/engine.git\n"
    )
    machine = FakeMachine(commands={(REPO, CONFIG_ARGV): CommandResult(0, config, "")})

    repo = collect_repo(machine, REPO, home=HOME)

    # origin wins even though it is listed after upstream.
    assert repo.github == "https://github.com/ada/engine"
