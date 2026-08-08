"""The editor Collector, driven over the fake seam with synthetic fixtures.

Exercises the assembled Section: VS Code installed with its version and the
installed extensions in listing order, and an absent CLI landing as a plain fact
rather than an error.
"""

from __future__ import annotations

import fixtures

from wkx_ecosystem_localhost.collectors.editor import collect_editor


def test_installed_editor_reports_version_and_extensions() -> None:
    section = collect_editor(fixtures.build_editor_workspace())

    assert section.installed is True
    assert section.version == "1.96.0"
    assert [(e.id, e.version) for e in section.extensions] == [
        ("ms-python.python", "2024.22.0"),
        ("esbenp.prettier-vscode", "11.0.0"),
        ("dbaeumer.vscode-eslint", "3.0.10"),
        ("charliermarsh.ruff", "2025.22.0"),
    ]


def test_absent_editor_reports_a_plain_fact_not_an_error() -> None:
    section = collect_editor(fixtures.build_editor_absent())

    assert section.installed is False
    assert section.version is None
    assert section.extensions == []
