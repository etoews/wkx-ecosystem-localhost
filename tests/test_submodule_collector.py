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
    collect_submodules,
    discover_submodules,
    probe_submodule,
    stream_submodule_probes,
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
