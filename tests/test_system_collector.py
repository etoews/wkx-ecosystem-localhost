"""The system Collector, driven over the fake seam with synthetic fixtures.

Exercises the assembled Section: each configured tool as present-with-version or
missing, in the configured order, an absent tool landing as a plain fact rather
than an error, and a tool added purely through configuration (with an overridden
version command) probed exactly as configured.
"""

from __future__ import annotations

import fixtures
from fakes import FakeMachine

from wkx_ecosystem_localhost.collectors.system import collect_system_tools
from wkx_ecosystem_localhost.config import ToolSpec


def _section() -> object:
    machine, tools = fixtures.build_system_workspace()
    return collect_system_tools(machine, tools)


def test_present_tools_report_their_parsed_version() -> None:
    section = _section()

    by_name = {tool.name: tool for tool in section.tools}
    assert by_name["git"].present is True
    assert by_name["git"].version == "2.39.5"
    assert by_name["docker"].version == "27.4.0"
    assert by_name["aws"].version == "2.22.19"
    assert by_name["node"].version == "22.12.0"


def test_an_absent_tool_is_reported_missing_not_errored() -> None:
    section = _section()

    ty = next(tool for tool in section.tools if tool.name == "ty")
    assert ty.present is False
    assert ty.version is None


def test_a_configuration_added_tool_is_probed_with_its_own_command() -> None:
    section = _section()

    widget = next(tool for tool in section.tools if tool.name == "widget")
    assert widget.present is True
    assert widget.version == "3.2.1"


def test_the_section_preserves_the_configured_order() -> None:
    section = _section()

    names = [tool.name for tool in section.tools]
    assert names == [spec.name for spec in fixtures.SYSTEM_TOOLS]


def test_adding_a_tool_by_configuration_changes_the_probe_with_no_code_change() -> None:
    machine, _tools = fixtures.build_system_workspace()

    # A caller that names only two tools gets exactly those two probed, in order:
    # the tool list is data the Collector consumes, never anything hard-coded.
    section = collect_system_tools(machine, [ToolSpec(name="node"), ToolSpec(name="git")])

    assert [tool.name for tool in section.tools] == ["node", "git"]
    assert section.tools[0].version == "22.12.0"
    assert section.tools[1].version == "2.39.5"


def test_an_empty_tool_list_yields_an_empty_section() -> None:
    assert collect_system_tools(FakeMachine(), []).tools == []
