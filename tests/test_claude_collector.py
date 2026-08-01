"""Collector-level tests for the claude Collector over the fake Machine.

Drive ``collect_claude`` directly against the synthetic fixture so the join of
manifest, marketplace, settings, and auth cache is pinned without the HTTP layer.
"""

from __future__ import annotations

import fixtures
from fakes import FakeMachine

from wkx_ecosystem_localhost.collectors.claude import collect_claude
from wkx_ecosystem_localhost.models import Skill


def _skill(skills: list[Skill], name: str) -> Skill:
    return next(skill for skill in skills if skill.name == name)


def test_collect_skills_carries_origin_and_enabled_state() -> None:
    machine, home = fixtures.build_claude_workspace()

    section = collect_claude(machine, home=home)

    names = {skill.name for skill in section.skills}
    assert {"tidy-repo", "scratch", "layout", "wireframe"} <= names
    # A user skill: user Origin, always enabled, front matter read.
    tidy = _skill(section.skills, "tidy-repo")
    assert tidy.origin == "user"
    assert tidy.enabled is True
    assert tidy.description == "Use when a working tree needs a quick, safe tidy-up."
    # A user skill with no front matter falls back to the directory name.
    assert _skill(section.skills, "scratch").description is None
    # A plugin skill: plugin Origin, enabled state mirrors the owning plugin.
    layout = _skill(section.skills, "layout")
    assert layout.origin == "tidy@studio-official"
    assert layout.enabled is True
    # A disabled plugin's skill is still shown, badged disabled.
    assert _skill(section.skills, "wireframe").enabled is False


def test_collect_plugins_joins_repo_version_and_enabled() -> None:
    machine, home = fixtures.build_claude_workspace()

    plugins = {plugin.name: plugin for plugin in collect_claude(machine, home=home).plugins}

    assert plugins["tidy"].repo == "acme/studio-official"
    assert plugins["tidy"].version == "2.3.0"
    assert plugins["tidy"].enabled is True
    assert plugins["tidy"].install_path == "~/.claude/plugins/cache/studio-official/tidy/2.3.0"
    # Disabled, but present and badged.
    assert plugins["sketch"].enabled is False
    assert plugins["sketch"].version == "unknown"
    # A non-GitHub marketplace has no repo; gizmo is enabled via settings.local.json.
    assert plugins["gizmo"].repo is None
    assert plugins["gizmo"].enabled is True


def test_collect_mcp_servers_span_origins_with_auth_state() -> None:
    machine, home = fixtures.build_claude_workspace()

    servers = {s.name: s for s in collect_claude(machine, home=home).mcp_servers}

    # A plugin server needing auth, and a plugin server not needing it.
    assert servers["cloud-mcp"].origin == "cloudkit@studio-official"
    assert servers["cloud-mcp"].transport == "http"
    assert servers["cloud-mcp"].needs_auth is True
    assert servers["local-mcp"].needs_auth is False
    # A user server (from the top-level config) needing auth by its bare name.
    assert servers["vault-mcp"].origin == "user"
    assert servers["vault-mcp"].needs_auth is True
    assert servers["notes-mcp"].origin == "user"
    # A project server.
    assert servers["repo-mcp"].origin == "project"


def test_collect_claude_never_surfaces_account_or_telemetry() -> None:
    machine, home = fixtures.build_claude_workspace()

    section = collect_claude(machine, home=home)

    blob = section.model_dump_json()
    assert "should-never-appear" not in blob
    assert "should-not-leak" not in blob
    assert fixtures.CLAUDE_SECRET not in blob


def test_collect_claude_empty_environment_is_empty_section() -> None:
    section = collect_claude(FakeMachine(), home=fixtures.HOME)

    assert section.skills == []
    assert section.plugins == []
    assert section.mcp_servers == []
