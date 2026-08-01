"""Pure-parser tests for the claude Collector.

Every input is synthetic, hand-written to pin one parsing edge case. No string
here is captured from a real machine, so the suite runs anywhere and the public
repo stays machine-neutral.
"""

from __future__ import annotations

from wkx_ecosystem_localhost.collectors.claude import (
    InstalledPlugin,
    McpServerSpec,
    classify_transport,
    parse_auth_cache,
    parse_enabled_plugins,
    parse_installed_plugins,
    parse_known_marketplaces,
    parse_mcp_servers,
    parse_skill_frontmatter,
    parse_user_config_mcp,
)

# ------------------------- skill front matter -------------------------

SKILL_MD = """\
---
name: tidy-repo
description: Use when a working tree needs a quick, safe tidy-up.
---

# tidy-repo

Body text that must never be read as front matter.
"""

SKILL_MD_NO_DESC = "---\nname: bare\n---\n\n# bare\n"
SKILL_MD_NO_FRONTMATTER = "# just a heading\n\nno front matter here\n"


def test_parse_skill_frontmatter_reads_name_and_description() -> None:
    name, description = parse_skill_frontmatter(SKILL_MD)

    assert name == "tidy-repo"
    assert description == "Use when a working tree needs a quick, safe tidy-up."


def test_parse_skill_frontmatter_missing_description_is_none() -> None:
    name, description = parse_skill_frontmatter(SKILL_MD_NO_DESC)

    assert name == "bare"
    assert description is None


def test_parse_skill_frontmatter_without_block_yields_nones() -> None:
    name, description = parse_skill_frontmatter(SKILL_MD_NO_FRONTMATTER)

    assert name is None
    assert description is None


# ------------------------- installed plugins -------------------------

INSTALLED_PLUGINS = """\
{
  "version": 2,
  "plugins": {
    "tidy@studio-official": [
      {
        "scope": "user",
        "installPath": "/home/.claude/plugins/cache/studio-official/tidy/2.3.0",
        "version": "2.3.0"
      }
    ],
    "sketch@studio-official": [
      {
        "scope": "user",
        "installPath": "/home/.claude/plugins/cache/studio-official/sketch/unknown",
        "version": "unknown"
      }
    ]
  }
}
"""


def test_parse_installed_plugins_splits_key_and_reads_version() -> None:
    plugins = parse_installed_plugins(INSTALLED_PLUGINS)

    assert plugins == [
        InstalledPlugin(
            key="tidy@studio-official",
            name="tidy",
            marketplace="studio-official",
            version="2.3.0",
            install_path="/home/.claude/plugins/cache/studio-official/tidy/2.3.0",
        ),
        InstalledPlugin(
            key="sketch@studio-official",
            name="sketch",
            marketplace="studio-official",
            version="unknown",
            install_path="/home/.claude/plugins/cache/studio-official/sketch/unknown",
        ),
    ]


def test_parse_installed_plugins_tolerates_malformed_json() -> None:
    assert parse_installed_plugins("{ not json") == []


# ------------------------- known marketplaces -------------------------

KNOWN_MARKETPLACES = """\
{
  "studio-official": {
    "source": {"source": "github", "repo": "acme/studio-official"},
    "installLocation": "/home/.claude/plugins/marketplaces/studio-official"
  },
  "local-shelf": {
    "source": {"source": "directory", "path": "/home/shelf"}
  }
}
"""


def test_parse_known_marketplaces_maps_github_repo() -> None:
    repos = parse_known_marketplaces(KNOWN_MARKETPLACES)

    assert repos["studio-official"] == "acme/studio-official"


def test_parse_known_marketplaces_non_github_source_has_no_repo() -> None:
    repos = parse_known_marketplaces(KNOWN_MARKETPLACES)

    assert repos["local-shelf"] is None


# ------------------------- enabled plugins -------------------------

SETTINGS = """\
{
  "model": "claude-opus-4-8",
  "enabledPlugins": {
    "tidy@studio-official": true,
    "sketch@studio-official": false
  }
}
"""


def test_parse_enabled_plugins_reads_the_map() -> None:
    enabled = parse_enabled_plugins(SETTINGS)

    assert enabled == {"tidy@studio-official": True, "sketch@studio-official": False}


def test_parse_enabled_plugins_absent_map_is_empty() -> None:
    assert parse_enabled_plugins('{"model": "x"}') == {}


# ------------------------- transport classification -------------------------


def test_classify_transport_prefers_explicit_type() -> None:
    assert classify_transport({"type": "sse", "url": "https://example.test"}) == "sse"


def test_classify_transport_url_without_type_is_http() -> None:
    assert classify_transport({"url": "https://example.test/mcp"}) == "http"


def test_classify_transport_command_is_stdio() -> None:
    assert classify_transport({"command": "uvx", "args": ["some-server"]}) == "stdio"


# ------------------------- mcp servers block -------------------------

PLUGIN_MCP = """\
{
  "mcpServers": {
    "widget-mcp": {"command": "uvx", "args": ["widget@1.0.0"]},
    "cloud-mcp": {"type": "http", "url": "https://example.test/mcp"}
  }
}
"""


def test_parse_mcp_servers_returns_name_and_transport_only() -> None:
    servers = parse_mcp_servers(PLUGIN_MCP)

    assert servers == [
        McpServerSpec(name="widget-mcp", transport="stdio"),
        McpServerSpec(name="cloud-mcp", transport="http"),
    ]


def test_parse_mcp_servers_malformed_json_is_empty() -> None:
    assert parse_mcp_servers("nope") == []


# ------------------------- auth cache -------------------------

AUTH_CACHE = '{"plugin:tidy:widget-mcp": {"timestamp": 1, "id": "abc"}, "cloud-mcp": {}}'


def test_parse_auth_cache_returns_key_set() -> None:
    keys = parse_auth_cache(AUTH_CACHE)

    assert keys == {"plugin:tidy:widget-mcp", "cloud-mcp"}


def test_parse_auth_cache_malformed_json_is_empty() -> None:
    assert parse_auth_cache("{oops") == set()


# ------------------------- narrow user-config read -------------------------
# The security-critical parser. The synthetic config carries the account,
# machine, and telemetry fields the narrow read must never touch, plus a token in
# a server's own config that must never leave the parser.

USER_CONFIG = """\
{
  "userID": "u-should-never-appear",
  "oauthAccount": {"emailAddress": "secret@should-not-leak.test"},
  "machineID": "m-should-never-appear",
  "telemetry": {"enabled": true, "token": "tel-should-never-appear"},
  "mcpServers": {
    "notes-mcp": {"command": "uvx", "args": ["notes@2.0.0"]},
    "vault-mcp": {
      "type": "http",
      "url": "https://vault.test/mcp",
      "headers": {"Authorization": "Bearer tok-should-never-appear"}
    }
  },
  "projects": {
    "/home/dev/acme": {
      "mcpServers": {"repo-mcp": {"command": "node", "args": ["server.js"]}}
    },
    "/home/dev/quiet": {
      "allowedTools": ["Bash"]
    }
  }
}
"""


def test_parse_user_config_mcp_reads_only_the_server_subset() -> None:
    user_servers, project_servers = parse_user_config_mcp(USER_CONFIG)

    assert user_servers == [
        McpServerSpec(name="notes-mcp", transport="stdio"),
        McpServerSpec(name="vault-mcp", transport="http"),
    ]
    assert project_servers == [McpServerSpec(name="repo-mcp", transport="stdio")]


def test_parse_user_config_mcp_never_surfaces_account_or_telemetry() -> None:
    user_servers, project_servers = parse_user_config_mcp(USER_CONFIG)

    blob = repr(user_servers) + repr(project_servers)
    assert "should-never-appear" not in blob
    assert "should-not-leak" not in blob
    assert "Bearer" not in blob


def test_parse_user_config_mcp_malformed_json_is_empty() -> None:
    assert parse_user_config_mcp("{broken") == ([], [])
