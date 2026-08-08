"""The submodule Collector: discovery, per-submodule probing, and the stream.

Every read goes through the fake seam. These pin discovery with the local pin
resolved, the three probe outcomes (a ladder with drift, pinned on the latest,
an unreachable remote), and the streaming pool that yields one event per
submodule keyed by its home-relative path.
"""

from __future__ import annotations

import fixtures
from fakes import FakeMachine

from wkx_ecosystem_localhost.collectors.submodules import (
    SubmoduleSpec,
    collect_submodules,
    discover_submodules,
    ls_remote_tags_argv,
    probe_submodule,
    releases_latest_argv,
    stream_submodule_probes,
)
from wkx_ecosystem_localhost.github import releases_latest_url
from wkx_ecosystem_localhost.machine import CommandResult


def _ok(stdout: str) -> CommandResult:
    return CommandResult(0, stdout, "")


def _github_spec(url: str = "https://github.com/acme/widgets.git") -> SubmoduleSpec:
    """A single GitHub submodule spec, pinned below its remote's tags."""
    return SubmoduleSpec(
        repo_path=fixtures.APP,
        name="libs/widgets",
        rel_path="libs/widgets",
        url=url,
        pinned="1.2.0",
    )


def _release_machine(spec: SubmoduleSpec, redirect: CommandResult) -> FakeMachine:
    """A machine that lists a 2.0.0 ladder for ``spec`` and answers its release curl."""
    release_url = releases_latest_url(spec.url)
    assert release_url is not None
    return FakeMachine(
        commands={
            (None, ls_remote_tags_argv(spec.url)): _ok(fixtures.LS_REMOTE_WIDGETS),
            (None, releases_latest_argv(release_url)): redirect,
        }
    )


def test_discover_submodules_resolves_each_pin_locally() -> None:
    machine, _home, _roots = fixtures.build_submodule_workspace()

    specs = discover_submodules(machine, [fixtures.APP, fixtures.API])

    by_name = {spec.name: spec for spec in specs}
    assert set(by_name) == {"libs/widgets", "tools/kit", "vendor/remote-gone"}
    assert by_name["libs/widgets"].pinned == "1.2.0"
    assert by_name["tools/kit"].url == fixtures.KIT_URL


def test_probe_reports_latest_and_tags_behind_for_a_drifted_submodule() -> None:
    machine, _, _ = fixtures.build_submodule_workspace()
    (spec,) = [s for s in discover_submodules(machine, [fixtures.APP]) if s.name == "libs/widgets"]

    outcome = probe_submodule(machine, spec)

    # Stable tags above 1.2.0 are 1.3.0 and 2.0.0; the 2.1.0-rc.1 pre-release is
    # excluded while a stable tag exists.
    assert outcome.latest == "2.0.0"
    assert outcome.behind == 2
    assert outcome.unknown is False


def test_probe_reports_zero_behind_when_pinned_on_the_latest_tag() -> None:
    machine, _, _ = fixtures.build_submodule_workspace()
    (spec,) = [s for s in discover_submodules(machine, [fixtures.APP]) if s.name == "tools/kit"]

    outcome = probe_submodule(machine, spec)

    assert outcome.latest == "v3.1.0"
    assert outcome.behind == 0


def test_probe_falls_to_unknown_when_the_remote_cannot_be_listed() -> None:
    machine, _, _ = fixtures.build_submodule_workspace()
    (spec,) = discover_submodules(machine, [fixtures.API])

    outcome = probe_submodule(machine, spec)

    assert outcome.unknown is True
    assert outcome.latest is None
    assert outcome.behind is None


def test_collect_submodules_pins_but_leaves_the_remote_truth_pending() -> None:
    machine, home, _roots = fixtures.build_submodule_workspace()

    section = collect_submodules(machine, [fixtures.APP, fixtures.API], home=home)

    by_path = {sub.path: sub for sub in section.submodules}
    widgets = by_path["~/dev/acme/app/libs/widgets"]
    assert widgets.pinned == "1.2.0"
    assert widgets.repo == "~/dev/acme/app"
    # latest and behind stay pending until the SSE probe lands.
    assert widgets.latest is None
    assert widgets.behind is None


def test_collect_submodules_links_github_remotes_only() -> None:
    machine, home, _roots = fixtures.build_submodule_workspace()

    section = collect_submodules(machine, [fixtures.APP, fixtures.API], home=home)

    by_name = {sub.name: sub for sub in section.submodules}
    # widgets is a GitHub remote, so it earns a link exposing only owner and repo;
    # kit and the unreachable submodule are non-GitHub, so they earn none.
    assert by_name["libs/widgets"].github == "https://github.com/acme/widgets"
    assert by_name["tools/kit"].github is None
    assert by_name["vendor/remote-gone"].github is None


def test_stream_yields_one_event_per_submodule_keyed_by_path() -> None:
    machine, home, _ = fixtures.build_submodule_workspace()

    events = list(
        stream_submodule_probes(machine, [fixtures.APP, fixtures.API], home=home, max_workers=4)
    )

    by_path = {event.submodule: event for event in events}
    assert set(by_path) == {
        "~/dev/acme/app/libs/widgets",
        "~/dev/acme/app/tools/kit",
        "~/dev/acme/api/vendor/remote-gone",
    }
    assert by_path["~/dev/acme/app/libs/widgets"].behind == 2
    assert by_path["~/dev/acme/api/vendor/remote-gone"].unknown is True


def test_stream_over_repos_without_submodules_yields_nothing() -> None:
    assert list(stream_submodule_probes(FakeMachine(), [], home=fixtures.HOME, max_workers=4)) == []


# ------------------------- GitHub release lookup (M9-B) -------------------------


def test_probe_surfaces_the_github_release_when_it_differs_from_the_tag_latest() -> None:
    machine, _, _ = fixtures.build_submodule_workspace()
    (spec,) = [s for s in discover_submodules(machine, [fixtures.APP]) if s.name == "libs/widgets"]

    outcome = probe_submodule(machine, spec)

    # GitHub blesses 1.3.0 while the highest semver tag is 2.0.0, so the release is
    # surfaced. The tag-based latest and behind are untouched by the lookup.
    assert outcome.github_release == "1.3.0"
    assert outcome.latest == "2.0.0"
    assert outcome.behind == 2


def test_probe_stays_quiet_when_the_github_release_agrees_with_the_tag_latest() -> None:
    spec = _github_spec()
    machine = _release_machine(spec, _ok("https://github.com/acme/widgets/releases/tag/2.0.0"))

    outcome = probe_submodule(machine, spec)

    # The blessed release names the same version already shown, so nothing extra.
    assert outcome.github_release is None
    assert outcome.latest == "2.0.0"
    assert outcome.behind == 2


def test_probe_stays_tag_based_for_a_release_less_repo() -> None:
    spec = _github_spec()
    # A repo with no release redirects to the bare releases page: no /tag/ segment.
    machine = _release_machine(spec, _ok("https://github.com/acme/widgets/releases"))

    outcome = probe_submodule(machine, spec)

    assert outcome.github_release is None
    assert outcome.latest == "2.0.0"


def test_probe_stays_tag_based_when_the_release_curl_fails() -> None:
    spec = _github_spec()
    # A rate limit, a timeout, or no network: curl exits non-zero and the row falls
    # back to the tag-based latest, never an error.
    machine = _release_machine(spec, CommandResult(6, "", "could not resolve host"))

    outcome = probe_submodule(machine, spec)

    assert outcome.github_release is None
    assert outcome.latest == "2.0.0"


def test_probe_does_not_look_up_a_release_for_a_non_github_submodule() -> None:
    spec = SubmoduleSpec(
        repo_path=fixtures.APP,
        name="tools/kit",
        rel_path="tools/kit",
        url=fixtures.KIT_URL,
        pinned="v3.1.0",
    )
    # Only the tag listing is registered; no release curl exists for kit. If the
    # probe tried one it would 127, but a non-GitHub remote never reaches the seam.
    machine = FakeMachine(
        commands={(None, ls_remote_tags_argv(fixtures.KIT_URL)): _ok(fixtures.LS_REMOTE_KIT)}
    )

    outcome = probe_submodule(machine, spec)

    assert outcome.github_release is None
    assert outcome.latest == "v3.1.0"


def test_lookup_release_is_never_passed_a_credential_from_the_remote() -> None:
    # A tokened GitHub remote: the curl argv must carry only the clean owner/repo
    # URL, so no secret can ride into the outbound request.
    spec = _github_spec(url="https://ada:ghp_secret@github.com/acme/widgets.git")
    release_url = releases_latest_url(spec.url)
    assert release_url == "https://github.com/acme/widgets/releases/latest"
    assert "ghp_secret" not in " ".join(releases_latest_argv(release_url))


def test_stream_carries_the_differing_release_and_leaves_the_others_none() -> None:
    machine, home, _ = fixtures.build_submodule_workspace()

    events = list(
        stream_submodule_probes(machine, [fixtures.APP, fixtures.API], home=home, max_workers=4)
    )
    by_path = {event.submodule: event for event in events}

    assert by_path["~/dev/acme/app/libs/widgets"].github_release == "1.3.0"
    # kit agrees to a non-GitHub remote and the unreachable one is unknown, so
    # neither carries a release.
    assert by_path["~/dev/acme/app/tools/kit"].github_release is None
    assert by_path["~/dev/acme/api/vendor/remote-gone"].github_release is None
