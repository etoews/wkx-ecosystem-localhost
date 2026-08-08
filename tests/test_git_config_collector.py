"""The git-config Collector, driven over the fake seam with synthetic fixtures.

Exercises the assembled Section: every key shown with targeted redaction, a
genuine single-valued conflict marking the shadowed earlier entry, a multi-valued
key that must never read as shadowed, an embedded credential stripped to its
endpoint and flagged, and the include directives resolved and existence-checked.
Redaction is proven by asserting the synthetic token never survives anywhere in
the Section.
"""

from __future__ import annotations

import fixtures

from wkx_ecosystem_localhost.collectors.git_config import collect_git_config
from wkx_ecosystem_localhost.models import GitConfigEntry


def _entries(section, key: str) -> list[GitConfigEntry]:
    return [entry for entry in section.entries if entry.key == key]


def test_identity_is_present_when_user_email_is_set() -> None:
    machine, home = fixtures.build_git_config_workspace()
    section = collect_git_config(machine, home=home)
    assert section.identity_present is True


def test_user_email_is_shown_unmasked() -> None:
    machine, home = fixtures.build_git_config_workspace()
    section = collect_git_config(machine, home=home)
    email = _entries(section, "user.email")
    assert len(email) == 1
    assert email[0].value == "ada@example.com"
    assert email[0].masked is False
    assert email[0].origin == "~/.gitconfig"


def test_single_valued_conflict_shadows_the_earlier_entry() -> None:
    machine, home = fixtures.build_git_config_workspace()
    section = collect_git_config(machine, home=home)
    editors = _entries(section, "core.editor")
    # git is last-wins, so the earlier value is the shadowed one.
    assert [(e.value, e.shadowed) for e in editors] == [("vim", True), ("code --wait", False)]


def test_multivar_duplicate_is_never_shadowed() -> None:
    machine, home = fixtures.build_git_config_workspace()
    section = collect_git_config(machine, home=home)
    insteadof = _entries(section, "url.git@github.com:.insteadof")
    assert len(insteadof) == 2
    assert all(entry.shadowed is False for entry in insteadof)


def test_embedded_credential_is_stripped_and_flagged() -> None:
    machine, home = fixtures.build_git_config_workspace()
    section = collect_git_config(machine, home=home)
    endpoint = _entries(section, "myservice.endpoint")
    assert len(endpoint) == 1
    assert endpoint[0].credentials is True
    # ADR 0001: the credential is stripped and the endpoint stays visible, not
    # masked whole; the red credentials Flag is what warns.
    assert endpoint[0].masked is False
    assert endpoint[0].value == "https://example.com/api"


def test_include_directives_are_resolved_and_existence_checked() -> None:
    machine, home = fixtures.build_git_config_workspace()
    section = collect_git_config(machine, home=home)
    by_path = {include.path: include for include in section.includes}

    present = by_path["~/.gitconfig-work"]
    assert present.condition is None
    assert present.exists is True

    broken = by_path["~/.gitconfig-missing"]
    assert broken.condition == "gitdir:~/work/"
    assert broken.exists is False


def test_include_directives_are_kept_out_of_the_entries_list() -> None:
    machine, home = fixtures.build_git_config_workspace()
    section = collect_git_config(machine, home=home)
    keys = {entry.key for entry in section.entries}
    assert "include.path" not in keys
    assert not any(key.startswith("includeif.") for key in keys)


def test_the_synthetic_token_never_survives_anywhere() -> None:
    machine, home = fixtures.build_git_config_workspace()
    section = collect_git_config(machine, home=home)
    blob = section.model_dump_json()
    assert fixtures.SECRET_TOKEN not in blob


def test_an_unreadable_probe_degrades_to_a_neutral_section() -> None:
    from fakes import FakeMachine

    section = collect_git_config(FakeMachine(), home=fixtures.HOME)
    assert section.entries == []
    assert section.includes == []
    assert section.identity_present is False
