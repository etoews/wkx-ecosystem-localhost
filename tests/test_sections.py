"""The Section enum, the Off switch, and the Hidden menu's server contract.

The enum and the ``sections_off`` validation are pinned directly; the Off
behaviour (route not registered, no Flags, repo discovery still shared) is driven
over HTTP against the same multi-repo fake the Flag layer uses, only the machine
seam faked, so the whole chain is exercised exactly as production would produce
it. app.js is not run by the suite, so Hidden is smoked in the board instead.
"""

from __future__ import annotations

from pathlib import Path

import fixtures
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from wkx_ecosystem_localhost.app import create_app
from wkx_ecosystem_localhost.config import Settings
from wkx_ecosystem_localhost.models import Section

STATIC = Path(__file__).parent.parent / "src" / "wkx_ecosystem_localhost" / "static"


# ---------- the enum ----------


def test_section_enum_is_the_ten_in_board_order() -> None:
    assert [section.value for section in Section] == [
        "workspace",
        "toolchains",
        "claude",
        "homebrew",
        "system",
        "docker",
        "footprint",
        "editor",
        "git-config",
        "config",
    ]


def test_each_section_value_is_a_panel_id_in_the_shell() -> None:
    # Every mount id in the shell must agree with the enum, or a Flag would badge a
    # Section the board cannot show and the Hidden menu would govern a missing panel.
    shell = (STATIC / "index.html").read_text()

    for section in Section:
        assert f'id="{section.value}"' in shell, section.value


def test_needs_attention_is_not_a_section() -> None:
    # Needs attention can be Hidden but never Off, so it is deliberately not a member.
    assert "summary" not in {section.value for section in Section}
    assert "needs-attention" not in {section.value for section in Section}


# ---------- sections_off validation ----------


def test_sections_off_defaults_to_empty() -> None:
    settings = Settings(_env_file=None, _config_file=None)

    assert settings.sections_off == []


def test_sections_off_accepts_known_section_names() -> None:
    settings = Settings(_env_file=None, _config_file=None, sections_off=["docker", "editor"])

    assert settings.sections_off == [Section.DOCKER, Section.EDITOR]


def test_sections_off_rejects_an_unknown_section_naming_it() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, _config_file=None, sections_off=["dockr"])

    assert "dockr" in str(excinfo.value)


def test_sections_off_rejects_config_because_it_is_the_bootstrap() -> None:
    # The config Section is the board's own effective-configuration view, which the
    # client boots from, so it is served unconditionally and can never be Off. Like
    # needs attention, it can be Hidden but not Off.
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, _config_file=None, sections_off=["config"])

    assert "config cannot be switched off" in str(excinfo.value)


def test_toml_sections_off_rejects_an_unknown_section(tmp_path: Path) -> None:
    path = tmp_path / "wkx-ecosystem-localhost.toml"
    path.write_text('sections_off = ["editr"]\n')

    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, _config_file=path)

    assert "editr" in str(excinfo.value)


def test_env_sections_off_reads_a_json_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WKX_ECO_LOCAL_SECTIONS_OFF", '["docker"]')

    settings = Settings(_env_file=None, _config_file=None)

    assert settings.sections_off == [Section.DOCKER]


# ---------- Off over HTTP ----------


def _off_client(*sections: Section) -> TestClient:
    """A flags-lighting fake with the given Sections switched off.

    The same multi-repo, multi-Origin fake the Flag layer uses, so an Off Section's
    Flags are demonstrably present when it is on and gone when it is off, all over
    the real app and Collectors with only the machine seam faked.
    """
    machine, home, roots, tools = fixtures.build_flags_workspace()
    settings = Settings(
        _env_file=None,
        _config_file=None,
        scan_roots=roots,
        system_tools=tools,
        sections_off=list(sections),
    )
    return TestClient(create_app(settings, machine=machine, home=home))


def test_off_section_route_is_not_registered() -> None:
    client = _off_client(Section.DOCKER)

    assert client.get("/api/docker").status_code == 404
    # A Section left on still serves.
    assert client.get("/api/system").status_code == 200


def test_off_section_carries_none_of_its_flags() -> None:
    client = _off_client(Section.DOCKER)

    flags = client.get("/api/flags").json()["flags"]
    sections = {flag["section"] for flag in flags}
    categories = {flag["category"] for flag in flags}

    assert "docker" not in sections
    assert "docker-unreachable" not in categories
    # The other Sections still raise their Flags, so the Off skip is surgical.
    assert ("system", "ty") in {(f["section"], f["target"]) for f in flags}


def test_config_lists_the_off_sections() -> None:
    client = _off_client(Section.DOCKER, Section.EDITOR)

    view = client.get("/api/config").json()

    assert view["sections_off"]["sections"] == ["docker", "editor"]


def test_workspace_off_still_discovers_repos_for_toolchains() -> None:
    client = _off_client(Section.WORKSPACE)

    # The workspace route is gone, but discovery still runs, so toolchains reads the
    # per-repo pins and their drift Flag is still derived.
    assert client.get("/api/workspace").status_code == 404
    toolchains = client.get("/api/toolchains")
    assert toolchains.status_code == 200
    assert toolchains.json()["python"]["repo_pins"], "discovery should still find the repos"

    categories = {flag["category"] for flag in client.get("/api/flags").json()["flags"]}
    assert "python-pin-drift" in categories
