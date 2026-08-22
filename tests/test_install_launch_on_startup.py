"""render_plist fills every placeholder and refuses to leave one behind.

The installer lives in scripts/ (not the package), so it is loaded from its path.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "install_launch_on_startup.py"


def _load_installer():
    spec = importlib.util.spec_from_file_location("install_launch_on_startup", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


installer = _load_installer()

_VALUES = {
    "LABEL": "dev.tester.wkx-ecosystem-localhost",
    "SHELL": "/bin/zsh",
    "UV_BIN": "/opt/homebrew/bin/uv",
    "PORT": "8787",
    "WORKING_DIR": "/Users/tester/dev/wkx-ecosystem-localhost",
    "LOG_PATH": "/Users/tester/Library/Logs/wkx-ecosystem-localhost.log",
}


def test_render_substitutes_every_placeholder() -> None:
    template = (
        "<string>${LABEL}</string>"
        "<string>${SHELL}</string>"
        "<string>exec ${UV_BIN} run wkx serve --port ${PORT}</string>"
        "<string>${WORKING_DIR}</string>"
        "<string>${LOG_PATH}</string>"
    )
    rendered = installer.render_plist(template, _VALUES)

    assert "$" not in rendered
    for value in _VALUES.values():
        assert value in rendered


def test_render_raises_on_unfilled_placeholder() -> None:
    template = "<string>${LABEL}</string><string>${MISSING}</string>"

    with pytest.raises(ValueError, match=r"MISSING"):
        installer.render_plist(template, {"LABEL": "x"})


def test_render_matches_the_committed_template() -> None:
    template = (_SCRIPT.parent / "wkx-ecosystem-localhost.plist.template").read_text()

    rendered = installer.render_plist(template, _VALUES)

    assert "$" not in rendered
    assert "<string>dev.tester.wkx-ecosystem-localhost</string>" in rendered
