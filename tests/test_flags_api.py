"""HTTP-level tests for the Flag layer.

Drives the real app and the real Collectors over the ``/api/flags`` endpoint,
with only the machine seam faked, so the whole layer is exercised end to end: the
Collectors run, ``derive_flags`` interprets their Sections, and the JSON contract
is produced exactly as production would. The fake is multi-repo and multi-Origin,
so the cross-item drift and shadowing Flags derive here too.
"""

from __future__ import annotations

import fixtures
from fastapi.testclient import TestClient

from wkx_ecosystem_localhost.app import create_app
from wkx_ecosystem_localhost.config import MuteRule, Settings


def _flag_index(flags: list[dict]) -> dict[tuple[str, str], set[str]]:
    """Group Flag categories by their (section, target) so a row's Flags read at a glance."""
    index: dict[tuple[str, str], set[str]] = {}
    for flag in flags:
        index.setdefault((flag["section"], flag["target"]), set()).add(flag["category"])
    return index


def test_flags_endpoint_returns_every_at_rest_flag(flags_client: TestClient) -> None:
    response = flags_client.get("/api/flags")
    assert response.status_code == 200
    flags = response.json()["flags"]
    index = _flag_index(flags)

    # Per-item workspace Flags, each on its own repo row.
    assert index[("workspace", "~/dev/acme/web")] == {"dirty-tree"}
    # api is detached at a modified work.py, so it is both detached and dirty.
    assert index[("workspace", "~/dev/acme/api")] == {"detached-head", "dirty-tree"}
    assert index[("workspace", "~/dev/acme/cli")] == {"no-upstream"}

    # Per-item Flags across the other Sections.
    assert index[("system", "ty")] == {"tool-missing"}
    assert index[("homebrew", "formula:wget")] == {"brew-outdated"}
    assert index[("homebrew", "cask:firefox")] == {"brew-outdated"}
    assert index[("docker", "daemon")] == {"docker-unreachable"}
    assert index[("claude", "plugin:sketch")] == {"plugin-disabled"}
    assert index[("claude", "mcp:cloud-mcp")] == {"mcp-needs-auth"}

    # A disabled plugin raises only its own plugin-disabled Flag: its wireframe
    # skill stays enabled on its own, so it raises no skill-disabled Flag.
    assert ("claude", "skill:wireframe") not in index
    # The lone skill-disabled trigger is a user skill set off in skillOverrides.
    assert index[("claude", "skill:muted-skill")] == {"skill-disabled"}


def test_flags_endpoint_derives_cross_item_drift(flags_client: TestClient) -> None:
    flags = flags_client.get("/api/flags").json()["flags"]
    index = _flag_index(flags)

    # Python pin drift badges both pinned repos.
    assert "python-pin-drift" in index[("toolchains", "pin:~/dev/acme/web")]
    assert "python-pin-drift" in index[("toolchains", "pin:~/dev/acme/api")]

    # TypeScript version drift badges the two repos with an installed version.
    assert "tool-version-drift" in index[("toolchains", "ts:~/dev/acme/web")]
    assert "tool-version-drift" in index[("toolchains", "ts:~/dev/acme/cli")]

    # The user "layout" skill shadows tidy's plugin "layout" across Origins.
    assert "skill-shadow" in index[("claude", "skill:layout")]

    # repo-mcp is configured under both the user and a project scope.
    assert "mcp-two-scopes" in index[("claude", "mcp:repo-mcp")]


def test_flags_endpoint_omits_the_sse_delivered_flags(flags_client: TestClient) -> None:
    # behind-remote and submodule-tags-behind need a background fetch, so the board
    # raises them as its SSE events land, never at rest.
    categories = {flag["category"] for flag in flags_client.get("/api/flags").json()["flags"]}
    assert "behind-remote" not in categories
    assert "submodule-tags-behind" not in categories


def test_flags_levels_are_the_two_levels_only(flags_client: TestClient) -> None:
    flags = flags_client.get("/api/flags").json()["flags"]
    assert flags, "the fixture should raise flags"
    assert {flag["level"] for flag in flags} <= {"attention", "problem"}
    # A missing tool, an unreachable daemon, and an MCP needing auth are problems.
    problems = {(f["section"], f["target"]) for f in flags if f["level"] == "problem"}
    assert ("system", "ty") in problems
    assert ("docker", "daemon") in problems
    assert ("claude", "mcp:cloud-mcp") in problems


def _muted_client(*rules: MuteRule) -> TestClient:
    """A flags-lighting client with the given Mute rules configured.

    The same multi-repo, multi-Origin fake the Flag layer uses, so /api/flags can be
    shown to still carry a muted Category and /api/config to carry the rules the
    client will apply.
    """
    machine, home, roots, tools = fixtures.build_flags_workspace()
    settings = Settings(
        _env_file=None,
        _config_file=None,
        scan_roots=roots,
        system_tools=tools,
        mute=list(rules),
    )
    return TestClient(create_app(settings, machine=machine, home=home))


def test_muted_flags_stay_on_the_wire() -> None:
    # Muting is a client-side view preference; the API is the inventory, so
    # /api/flags reports every Flag even for a muted Category and target.
    client = _muted_client(
        MuteRule(category="brew-outdated"),
        MuteRule(category="dirty-tree", target="~/dev/acme/web"),
    )

    categories = {f["category"] for f in client.get("/api/flags").json()["flags"]}

    assert "brew-outdated" in categories
    # The whole-category mute does not strip the flag from the inventory either.
    index = _flag_index(client.get("/api/flags").json()["flags"])
    assert "dirty-tree" in index[("workspace", "~/dev/acme/web")]


def test_config_carries_the_mute_rules_for_the_client() -> None:
    # The rules the client applies ride on /api/config, both a whole-category rule
    # and a targeted one, in order, with the target left None when absent.
    client = _muted_client(
        MuteRule(category="brew-outdated"),
        MuteRule(category="dirty-tree", target="~/dev/acme/web"),
    )

    view = client.get("/api/config").json()

    assert view["mute"]["source"] == "default"
    assert view["mute"]["rules"] == [
        {"category": "brew-outdated", "target": None},
        {"category": "dirty-tree", "target": "~/dev/acme/web"},
    ]
