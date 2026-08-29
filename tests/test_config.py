"""Settings behaviour: computed defaults, precedence across the sources, and fail-fast.

Every construction opts out of both file sources (``_env_file=None`` for ``.env``,
``_config_file=None`` for the TOML) unless the test is specifically exercising a
file, so the suite never reads a real configuration file on the host it runs on.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from wkx_ecosystem_localhost.config import (
    ENV_PREFIX,
    Settings,
    check_environment,
    describe,
    resolve_config_file,
)
from wkx_ecosystem_localhost.exceptions import ConfigError
from wkx_ecosystem_localhost.models import Section


def test_defaults_are_computed_not_literal() -> None:
    settings = Settings(_env_file=None, _config_file=None)

    assert settings.scan_roots == [Path.home() / "dev"]
    assert settings.scan_depth == 8
    assert settings.port == 8787


def test_discovery_cache_ttl_defaults_and_shows_in_the_config_view() -> None:
    settings = Settings(_env_file=None, _config_file=None)

    view = describe(settings, home=Path("/home/someone"), config_file=None, environ={})

    assert settings.discovery_cache_ttl == 60.0
    by_key = {item.key: item for item in view.values}
    assert by_key["discovery_cache_ttl"].value == "60.0"
    assert by_key["discovery_cache_ttl"].source == "default"


def test_env_overrides_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WKX_ECO_LOCAL_PORT", "9001")

    settings = Settings(_env_file=None, _config_file=None)

    assert settings.port == 9001


def test_env_overrides_scan_roots(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WKX_ECO_LOCAL_SCAN_ROOTS", '["/somewhere/else"]')

    settings = Settings(_env_file=None, _config_file=None)

    assert settings.scan_roots == [Path("/somewhere/else")]


def test_default_system_tools_is_the_generic_list() -> None:
    settings = Settings(_env_file=None, _config_file=None)

    names = [tool.name for tool in settings.system_tools]
    assert names == [
        "git",
        "gh",
        "uv",
        "ruff",
        "ty",
        "pre-commit",
        "docker",
        "terraform",
        "aws",
        "code",
        "node",
    ]
    # Each tool defaults to the --version probe every generic tool understands.
    assert all(tool.version_args == ("--version",) for tool in settings.system_tools)


def test_env_extends_system_tools_without_code_change(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "WKX_ECO_LOCAL_SYSTEM_TOOLS",
        '[{"name": "kubectl"}, {"name": "just", "version_args": ["--version"]}]',
    )

    settings = Settings(_env_file=None, _config_file=None)

    assert [tool.name for tool in settings.system_tools] == ["kubectl", "just"]
    assert settings.system_tools[0].argv() == ("kubectl", "--version")


def test_default_exclude_is_empty() -> None:
    settings = Settings(_env_file=None, _config_file=None)

    assert settings.exclude == []


def test_env_sets_exclude_as_a_json_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WKX_ECO_LOCAL_EXCLUDE", '["~/dev/experiments", "**/vendor"]')

    settings = Settings(_env_file=None, _config_file=None)

    assert settings.exclude == ["~/dev/experiments", "**/vendor"]


def test_unknown_argument_is_rejected() -> None:
    # extra="forbid" guards explicit construction. The separate startup scan
    # (test below) is what catches a misspelt WKX_ECO_LOCAL_* variable, which the
    # env source silently ignores on its own.
    with pytest.raises(ValidationError):
        Settings(_env_file=None, _config_file=None, prot=9001)


# ---------- TOML file source ----------


def _write_toml(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "wkx-ecosystem-localhost.toml"
    path.write_text(body)
    return path


def test_missing_file_yields_the_computed_defaults(tmp_path: Path) -> None:
    absent = tmp_path / "nope.toml"

    settings = Settings(_env_file=None, _config_file=absent)

    assert settings.port == 8787
    assert settings.scan_roots == [Path.home() / "dev"]


def test_toml_values_are_read(tmp_path: Path) -> None:
    path = _write_toml(tmp_path, "port = 9100\nscan_depth = 3\n")

    settings = Settings(_env_file=None, _config_file=path)

    assert settings.port == 9100
    assert settings.scan_depth == 3


def test_toml_paths_accept_tilde(tmp_path: Path) -> None:
    path = _write_toml(tmp_path, 'scan_roots = ["~/code", "~/work"]\n')

    settings = Settings(_env_file=None, _config_file=path)

    assert settings.scan_roots == [Path.home() / "code", Path.home() / "work"]


def test_env_path_accepts_tilde(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WKX_ECO_LOCAL_SCAN_ROOTS", '["~/code"]')

    settings = Settings(_env_file=None, _config_file=None)

    assert settings.scan_roots == [Path.home() / "code"]


def test_toml_system_tools_table(tmp_path: Path) -> None:
    path = _write_toml(
        tmp_path,
        '[[system_tools]]\nname = "kubectl"\n\n'
        '[[system_tools]]\nname = "just"\nversion_args = ["--version"]\n',
    )

    settings = Settings(_env_file=None, _config_file=path)

    assert [tool.name for tool in settings.system_tools] == ["kubectl", "just"]


def test_toml_sets_exclude(tmp_path: Path) -> None:
    path = _write_toml(tmp_path, 'exclude = ["~/dev/experiments", "**/vendor"]\n')

    settings = Settings(_env_file=None, _config_file=path)

    assert settings.exclude == ["~/dev/experiments", "**/vendor"]


def test_unknown_toml_key_fails_naming_it(tmp_path: Path) -> None:
    path = _write_toml(tmp_path, "prot = 9001\n")

    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, _config_file=path)

    assert "prot" in str(excinfo.value)


def test_config_file_env_override_selects_the_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = _write_toml(tmp_path, "port = 9200\n")
    monkeypatch.setenv("WKX_ECO_LOCAL_CONFIG_FILE", str(path))

    # No explicit _config_file, so the env-only override selects the file.
    settings = Settings(_env_file=None)

    assert settings.port == 9200


def test_config_file_env_variable_is_not_a_field(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # WKX_ECO_LOCAL_CONFIG_FILE names the file the fields are read from, so it is
    # not itself a field and never trips the unknown-variable scan.
    monkeypatch.setenv("WKX_ECO_LOCAL_CONFIG_FILE", str(tmp_path / "x.toml"))

    check_environment()  # does not raise


# ---------- precedence ----------


def test_argument_beats_environment_beats_toml(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = _write_toml(tmp_path, "port = 9100\nscan_depth = 3\n")
    monkeypatch.setenv("WKX_ECO_LOCAL_PORT", "9200")

    settings = Settings(_env_file=None, _config_file=path, port=9300)

    # Explicit argument wins over the environment, which wins over the TOML.
    assert settings.port == 9300
    # scan_depth is set only in the TOML, so the file value stands.
    assert settings.scan_depth == 3


def test_environment_beats_toml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = _write_toml(tmp_path, "port = 9100\n")
    monkeypatch.setenv("WKX_ECO_LOCAL_PORT", "9200")

    settings = Settings(_env_file=None, _config_file=path)

    assert settings.port == 9200


def test_toml_beats_default(tmp_path: Path) -> None:
    path = _write_toml(tmp_path, "port = 9100\n")

    settings = Settings(_env_file=None, _config_file=path)

    assert settings.port == 9100


def test_dotenv_beats_toml(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("WKX_ECO_LOCAL_PORT=9400\n")
    toml = _write_toml(tmp_path, "port = 9100\n")

    settings = Settings(_env_file=env_file, _config_file=toml)

    # .env sits above the TOML in the precedence chain.
    assert settings.port == 9400


def test_dotenv_rejects_an_unknown_prefixed_key(tmp_path: Path) -> None:
    # Unlike the environment source (which reads declared fields only and ignores
    # a stray variable, hence the startup scan), the dotenv source reads every
    # prefixed key from the file, so extra="forbid" rejects a misspelt one and
    # names it. This pins that divergence.
    env_file = tmp_path / ".env"
    env_file.write_text("WKX_ECO_LOCAL_PROT=9400\n")

    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=env_file, _config_file=None)

    assert "prot" in str(excinfo.value).lower()


# ---------- fail-fast environment scan ----------


def test_unknown_env_variable_raises_naming_it() -> None:
    with pytest.raises(ConfigError) as excinfo:
        check_environment({"WKX_ECO_LOCAL_PROT": "9001"})

    assert "WKX_ECO_LOCAL_PROT" in str(excinfo.value)


def test_known_env_variables_pass_the_scan() -> None:
    check_environment({"WKX_ECO_LOCAL_PORT": "9001", "WKX_ECO_LOCAL_SCAN_DEPTH": "3"})


def test_scan_ignores_unrelated_variables() -> None:
    check_environment({"PATH": "/usr/bin", "HOME": "/home/someone"})


def test_scan_logs_the_unknown_variable(caplog: pytest.LogCaptureFixture) -> None:
    with (
        caplog.at_level("ERROR", logger="wkx_ecosystem_localhost.config"),
        pytest.raises(ConfigError),
    ):
        check_environment({"WKX_ECO_LOCAL_TYPO": "x"})

    assert "WKX_ECO_LOCAL_TYPO" in caplog.text


# ---------- resolve_config_file ----------


def test_resolve_defaults_to_the_working_directory_file() -> None:
    assert resolve_config_file({}) == Path("wkx-ecosystem-localhost.toml")


def test_resolve_honours_the_env_override() -> None:
    resolved = resolve_config_file({"WKX_ECO_LOCAL_CONFIG_FILE": "~/custom.toml"})

    assert resolved == Path.home() / "custom.toml"


def test_resolve_none_opts_out() -> None:
    assert resolve_config_file({}, None) is None


# ---------- describe: the /api/config view model ----------


def test_describe_tags_defaults_when_no_file() -> None:
    settings = Settings(_env_file=None, _config_file=None)
    home = Path("/home/someone")

    view = describe(settings, home=home, config_file=None, environ={})

    assert view.file is None
    assert view.found is False
    by_key = {item.key: item for item in view.values}
    assert by_key["port"].value == "8787"
    assert all(item.source == "default" for item in view.values)
    assert view.system_tools.source == "default"


def test_describe_tags_the_file_source(tmp_path: Path) -> None:
    path = _write_toml(tmp_path, "port = 9100\n")
    settings = Settings(_env_file=None, _config_file=path)
    home = Path("/home/someone")

    view = describe(settings, home=home, config_file=path, environ={})

    assert view.found is True
    by_key = {item.key: item for item in view.values}
    assert by_key["port"].source == "file"
    assert by_key["port"].value == "9100"
    # scan_depth is untouched by the file, so it reads as a default.
    assert by_key["scan_depth"].source == "default"


def test_describe_tags_the_env_source(tmp_path: Path) -> None:
    path = _write_toml(tmp_path, "port = 9100\n")
    settings = Settings(_env_file=None, _config_file=path, port=9300)
    home = Path("/home/someone")

    view = describe(
        settings,
        home=home,
        config_file=path,
        environ={"WKX_ECO_LOCAL_PORT": "9300"},
    )

    by_key = {item.key: item for item in view.values}
    # Environment beats the file, so the value reads as env even though the file
    # also sets the key.
    assert by_key["port"].source == "env"


def test_describe_carries_empty_excludes_by_default() -> None:
    settings = Settings(_env_file=None, _config_file=None)
    home = Path("/home/someone")

    view = describe(settings, home=home, config_file=None, environ={})

    assert view.exclude.source == "default"
    assert view.exclude.globs == []


def test_describe_tags_the_exclude_block_from_the_file(tmp_path: Path) -> None:
    path = _write_toml(tmp_path, 'exclude = ["~/dev/experiments", "**/vendor"]\n')
    settings = Settings(_env_file=None, _config_file=path)
    home = Path("/home/someone")

    view = describe(settings, home=home, config_file=path, environ={})

    assert view.exclude.source == "file"
    assert view.exclude.globs == ["~/dev/experiments", "**/vendor"]


def test_describe_relativises_scan_roots() -> None:
    home = Path("/home/someone")
    settings = Settings(_env_file=None, _config_file=None, scan_roots=[home / "dev"])

    view = describe(settings, home=home, config_file=None, environ={})

    by_key = {item.key: item for item in view.values}
    assert by_key["scan_roots"].value == "~/dev"


def test_describe_relativises_the_file_path() -> None:
    home = Path("/home/someone")
    config_file = home / "wkx-ecosystem-localhost.toml"
    settings = Settings(_env_file=None, _config_file=None)

    view = describe(settings, home=home, config_file=config_file, environ={})

    assert view.file == "~/wkx-ecosystem-localhost.toml"


def test_env_prefix_is_wkx_eco_local() -> None:
    assert ENV_PREFIX == "WKX_ECO_LOCAL_"


# ---------- describe: the sections_off block ----------


def test_describe_reports_no_off_sections_by_default() -> None:
    settings = Settings(_env_file=None, _config_file=None)

    view = describe(settings, home=Path("/home/someone"), config_file=None, environ={})

    assert view.sections_off.sections == []
    assert view.sections_off.source == "default"


def test_describe_reports_the_off_sections_from_the_file(tmp_path: Path) -> None:
    path = tmp_path / "wkx-ecosystem-localhost.toml"
    path.write_text('sections_off = ["docker", "editor"]\n')
    settings = Settings(_env_file=None, _config_file=path)

    view = describe(settings, home=Path("/home/someone"), config_file=path, environ={})

    assert view.sections_off.sections == [Section.DOCKER, Section.EDITOR]
    assert view.sections_off.source == "file"
