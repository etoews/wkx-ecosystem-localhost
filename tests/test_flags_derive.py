"""Pure tests for the Flag layer's derivation.

``derive_flags`` is a pure function over the Section models, so every per-item and
cross-item Flag is pinned here against hand-written synthetic Sections, with no
machine and no HTTP in the way. The cross-item drift Flags are driven from
multi-repo Sections, exactly as CONTEXT.md defines them.
"""

from __future__ import annotations

import re
from collections.abc import Collection
from pathlib import Path

import pytest
from pydantic import ValidationError

from wkx_ecosystem_localhost.collectors.flags import ATTENTION, CATEGORIES, PROBLEM, derive_flags
from wkx_ecosystem_localhost.config import MuteRule, Settings
from wkx_ecosystem_localhost.models import (
    ClaudeSection,
    DockerSection,
    GitConfigEntry,
    GitConfigSection,
    GitInclude,
    HomebrewSection,
    McpServer,
    NodeToolchain,
    OutdatedPackage,
    Plugin,
    PythonToolchain,
    Repo,
    RepoPin,
    RepoTypeScript,
    Section,
    Skill,
    SystemToolsSection,
    Tool,
    ToolchainsSection,
    UvPython,
    WorkspaceSection,
)


def _repo(
    path: str,
    *,
    branch: str | None = "main",
    detached_sha: str | None = None,
    upstream: str | None = "origin/main",
    dirty: bool = False,
) -> Repo:
    return Repo(
        name=path.rsplit("/", 1)[-1],
        path=path,
        branch=branch,
        detached_sha=detached_sha,
        upstream=upstream,
        staged=0,
        unstaged=0,
        untracked=0,
        unmerged=0,
        stashes=0,
        dirty=dirty,
        config=[],
    )


def _workspace(*repos: Repo) -> WorkspaceSection:
    return WorkspaceSection(roots=["~/dev"], repos=list(repos))


def _system(*tools: Tool) -> SystemToolsSection:
    return SystemToolsSection(tools=list(tools))


def _toolchains(
    *,
    repo_pins: list[RepoPin] | None = None,
    ts_repos: list[RepoTypeScript] | None = None,
) -> ToolchainsSection:
    return ToolchainsSection(
        python=PythonToolchain(
            interpreters=[UvPython(implementation="cpython", version="3.14.4", installed=True)],
            global_pin="3.14.4",
            repo_pins=repo_pins or [],
            system=Tool(name="python3", version="3.14.4", present=True),
        ),
        node=NodeToolchain(
            node=Tool(name="node", version="24.0.0", present=True),
            npm=Tool(name="npm", version="11.0.0", present=True),
            tsc=Tool(name="tsc", version=None, present=False),
            package_managers=[],
            repos=ts_repos or [],
        ),
    )


def _claude(
    *,
    skills: list[Skill] | None = None,
    plugins: list[Plugin] | None = None,
    mcp_servers: list[McpServer] | None = None,
) -> ClaudeSection:
    return ClaudeSection(
        skills=skills or [],
        plugins=plugins or [],
        mcp_servers=mcp_servers or [],
    )


def _empty_homebrew() -> HomebrewSection:
    return HomebrewSection(present=True, formulae=[], casks=[])


def _up_docker() -> DockerSection:
    return DockerSection(daemon_reachable=True)


def _clean_git_config() -> GitConfigSection:
    """A quiet git-config Section: an identity present and nothing anomalous."""
    return GitConfigSection(entries=[], includes=[], identity_present=True)


def _git_config(
    *,
    entries: list[GitConfigEntry] | None = None,
    includes: list[GitInclude] | None = None,
    identity_present: bool = True,
) -> GitConfigSection:
    return GitConfigSection(
        entries=entries or [],
        includes=includes or [],
        identity_present=identity_present,
    )


def _derive(
    *,
    workspace: WorkspaceSection | None = None,
    toolchains: ToolchainsSection | None = None,
    system: SystemToolsSection | None = None,
    claude: ClaudeSection | None = None,
    homebrew: HomebrewSection | None = None,
    docker: DockerSection | None = None,
    git_config: GitConfigSection | None = None,
    off: Collection[Section] = (),
) -> list:
    return derive_flags(
        workspace=workspace or _workspace(),
        toolchains=toolchains or _toolchains(),
        system=system or _system(),
        claude=claude or _claude(),
        homebrew=homebrew or _empty_homebrew(),
        docker=docker or _up_docker(),
        git_config=git_config or _clean_git_config(),
        off=off,
    )


def _categories_for(flags: list, section: str, target: str) -> set[str]:
    return {f.category for f in flags if f.section == section and f.target == target}


# ------------------------- the zero case -------------------------


def test_no_flags_when_everything_is_quiet() -> None:
    clean = _workspace(_repo("~/dev/acme/web", dirty=False))
    assert _derive(workspace=clean) == []


# ------------------------- per-item workspace Flags -------------------------


def test_dirty_tree_flag_badges_the_repo_row() -> None:
    flags = _derive(workspace=_workspace(_repo("~/dev/acme/web", dirty=True)))
    dirty = [f for f in flags if f.category == "dirty-tree"]
    assert len(dirty) == 1
    assert dirty[0].section == "workspace"
    assert dirty[0].target == "~/dev/acme/web"
    assert dirty[0].level == ATTENTION


def test_detached_head_flag() -> None:
    repo = _repo("~/dev/acme/api", branch=None, detached_sha="3333333", upstream=None)
    flags = _derive(workspace=_workspace(repo))
    assert _categories_for(flags, "workspace", "~/dev/acme/api") == {"detached-head"}


def test_no_upstream_flag_only_on_a_branch_without_upstream() -> None:
    repo = _repo("~/dev/acme/cli", branch="wip", upstream=None)
    flags = _derive(workspace=_workspace(repo))
    assert _categories_for(flags, "workspace", "~/dev/acme/cli") == {"no-upstream"}


def test_a_repo_can_carry_more_than_one_flag() -> None:
    repo = _repo("~/dev/acme/web", branch="wip", upstream=None, dirty=True)
    flags = _derive(workspace=_workspace(repo))
    assert _categories_for(flags, "workspace", "~/dev/acme/web") == {"dirty-tree", "no-upstream"}


# ------------------------- Homebrew -------------------------


def test_brew_outdated_flags_each_package_keyed_by_kind() -> None:
    brew = HomebrewSection(
        present=True,
        formulae=[OutdatedPackage(name="wget", installed="1.21.3", current="1.21.4")],
        casks=[OutdatedPackage(name="firefox", installed="120.0", current="121.0")],
    )
    flags = _derive(homebrew=brew)
    outdated = [f for f in flags if f.category == "brew-outdated"]
    assert {f.target for f in outdated} == {"formula:wget", "cask:firefox"}
    assert all(f.level == ATTENTION for f in outdated)


def test_absent_homebrew_raises_no_flag() -> None:
    assert _derive(homebrew=HomebrewSection(present=False)) == []


# ------------------------- Docker -------------------------


def test_docker_unreachable_is_a_problem_flag() -> None:
    flags = _derive(docker=DockerSection(daemon_reachable=False))
    assert len(flags) == 1
    assert flags[0].category == "docker-unreachable"
    assert flags[0].section == "docker"
    assert flags[0].target == "daemon"
    assert flags[0].level == PROBLEM


# ------------------------- system tools -------------------------


def test_missing_configured_tool_is_a_problem_flag() -> None:
    system = _system(
        Tool(name="git", version="2.39.5", present=True),
        Tool(name="ty", version=None, present=False),
    )
    flags = _derive(system=system)
    assert len(flags) == 1
    assert flags[0].category == "tool-missing"
    assert flags[0].target == "ty"
    assert flags[0].level == PROBLEM


# ------------------------- Claude per-item -------------------------


def test_disabled_skill_and_plugin_flags() -> None:
    claude = _claude(
        skills=[Skill(name="wireframe", origin="sketch@studio", enabled=False)],
        plugins=[Plugin(name="sketch", marketplace="studio", version="1.0.0", enabled=False)],
    )
    flags = _derive(claude=claude)
    assert _categories_for(flags, "claude", "skill:wireframe") == {"skill-disabled"}
    assert _categories_for(flags, "claude", "plugin:sketch") == {"plugin-disabled"}
    assert all(f.level == ATTENTION for f in flags)


def test_mcp_needs_auth_is_a_problem_flag() -> None:
    claude = _claude(
        mcp_servers=[McpServer(name="cloud-mcp", origin="user", transport="http", needs_auth=True)]
    )
    flags = _derive(claude=claude)
    assert len(flags) == 1
    assert flags[0].category == "mcp-needs-auth"
    assert flags[0].target == "mcp:cloud-mcp"
    assert flags[0].level == PROBLEM


# ------------------------- cross-item drift (multi-repo) -------------------------


def test_python_pin_drift_flags_every_repo_pin() -> None:
    toolchains = _toolchains(
        repo_pins=[
            RepoPin(repo="~/dev/acme/web", version="3.14.4"),
            RepoPin(repo="~/dev/acme/api", version="3.13.13"),
        ]
    )
    flags = _derive(toolchains=toolchains)
    drift = [f for f in flags if f.category == "python-pin-drift"]
    assert {f.target for f in drift} == {"pin:~/dev/acme/web", "pin:~/dev/acme/api"}
    assert all(f.section == "toolchains" and f.level == ATTENTION for f in drift)


def test_no_python_pin_drift_when_all_repos_agree() -> None:
    toolchains = _toolchains(
        repo_pins=[
            RepoPin(repo="~/dev/acme/web", version="3.14.4"),
            RepoPin(repo="~/dev/acme/api", version="3.14.4"),
        ]
    )
    assert [f for f in _derive(toolchains=toolchains) if f.category == "python-pin-drift"] == []


def test_typescript_version_drift_flags_repos_with_an_installed_version() -> None:
    toolchains = _toolchains(
        ts_repos=[
            RepoTypeScript(repo="~/dev/acme/web", declared="^5.4.0", installed="5.3.3"),
            RepoTypeScript(repo="~/dev/acme/app", declared="^5.4.0", installed="5.4.5"),
            RepoTypeScript(repo="~/dev/acme/api", declared="~5.2.0", installed=None),
        ]
    )
    flags = _derive(toolchains=toolchains)
    drift = [f for f in flags if f.category == "tool-version-drift"]
    # api declares but has nothing installed, so it is not part of the drift.
    assert {f.target for f in drift} == {"ts:~/dev/acme/web", "ts:~/dev/acme/app"}


def test_no_typescript_drift_when_a_single_version_is_installed() -> None:
    toolchains = _toolchains(
        ts_repos=[
            RepoTypeScript(repo="~/dev/acme/web", declared="^5.4.0", installed="5.4.5"),
            RepoTypeScript(repo="~/dev/acme/app", declared="^5.4.0", installed="5.4.5"),
        ]
    )
    assert [f for f in _derive(toolchains=toolchains) if f.category == "tool-version-drift"] == []


def test_skill_name_shadowing_across_origins_flags_both_skills() -> None:
    claude = _claude(
        skills=[
            Skill(name="layout", origin="user", enabled=True),
            Skill(name="layout", origin="tidy@studio-official", enabled=True),
            Skill(name="tidy-repo", origin="user", enabled=True),
        ]
    )
    flags = _derive(claude=claude)
    shadow = [f for f in flags if f.category == "skill-shadow"]
    assert len(shadow) == 2
    assert all(f.target == "skill:layout" for f in shadow)
    # tidy-repo is unique, so it is never shadowed.
    assert "skill:tidy-repo" not in {f.target for f in shadow}


def test_same_skill_name_within_one_origin_is_not_shadowing() -> None:
    claude = _claude(
        skills=[
            Skill(name="layout", origin="user", enabled=True),
            Skill(name="layout", origin="user", enabled=True),
        ]
    )
    assert [f for f in _derive(claude=claude) if f.category == "skill-shadow"] == []


def test_mcp_configured_in_two_scopes_flags_the_server_once() -> None:
    claude = _claude(
        mcp_servers=[
            McpServer(name="repo-mcp", origin="user", transport="stdio", needs_auth=False),
            McpServer(name="repo-mcp", origin="project", transport="stdio", needs_auth=False),
            McpServer(name="notes-mcp", origin="user", transport="stdio", needs_auth=False),
        ]
    )
    flags = _derive(claude=claude)
    two_scope = [f for f in flags if f.category == "mcp-two-scopes"]
    assert len(two_scope) == 1
    assert two_scope[0].target == "mcp:repo-mcp"
    assert two_scope[0].level == ATTENTION


# ------------------------- git-config -------------------------


def _entry(
    key: str,
    value: str,
    *,
    credentials: bool = False,
    shadowed: bool = False,
    masked: bool = False,
) -> GitConfigEntry:
    return GitConfigEntry(
        key=key,
        value=value,
        origin="~/.gitconfig",
        masked=masked,
        shadowed=shadowed,
        credentials=credentials,
    )


def test_git_config_conflict_flags_a_single_valued_key_set_two_ways() -> None:
    git_config = _git_config(
        entries=[
            _entry("core.editor", "vim", shadowed=True),
            _entry("core.editor", "code --wait"),
        ]
    )
    flags = _derive(git_config=git_config)
    conflict = [f for f in flags if f.category == "git-config-conflict"]
    assert len(conflict) == 1
    assert conflict[0].section == "git-config"
    assert conflict[0].target == "core.editor"
    assert conflict[0].level == ATTENTION


def test_git_config_conflict_ignores_a_multivalued_key() -> None:
    # A real-machine regression: url.<base>.insteadof legitimately appears twice
    # with different values and must never read as a conflict.
    name = "url.git@github.com:.insteadof"
    git_config = _git_config(
        entries=[
            _entry(name, "https://github.com/"),
            _entry(name, "git://github.com/"),
        ]
    )
    assert [f for f in _derive(git_config=git_config) if f.category == "git-config-conflict"] == []


def test_git_config_conflict_ignores_a_duplicate_with_the_same_value() -> None:
    git_config = _git_config(
        entries=[
            _entry("user.name", "Ada Lovelace"),
            _entry("user.name", "Ada Lovelace"),
        ]
    )
    assert [f for f in _derive(git_config=git_config) if f.category == "git-config-conflict"] == []


def test_git_config_conflict_catches_a_masked_key_set_two_ways() -> None:
    # Two raw values that both redact to bullets still conflict: the Collector
    # marks the earlier entry shadowed from the raw values, so the Flag fires even
    # though the two display values are identical.
    name = "http.https://host/.extraheader"
    git_config = _git_config(
        entries=[
            _entry(name, "•••", masked=True, shadowed=True),
            _entry(name, "•••", masked=True),
        ]
    )
    conflict = [f for f in _derive(git_config=git_config) if f.category == "git-config-conflict"]
    assert len(conflict) == 1
    assert conflict[0].target == name


def test_git_include_broken_is_a_problem_flag() -> None:
    git_config = _git_config(
        includes=[
            GitInclude(condition=None, path="~/.gitconfig-work", exists=True),
            GitInclude(condition="gitdir:~/work/", path="~/.gitconfig-missing", exists=False),
        ]
    )
    flags = _derive(git_config=git_config)
    broken = [f for f in flags if f.category == "git-include-broken"]
    assert len(broken) == 1
    assert broken[0].section == "git-config"
    assert broken[0].target == "~/.gitconfig-missing"
    assert broken[0].level == PROBLEM


def test_git_config_credentials_is_a_problem_flag() -> None:
    git_config = _git_config(
        entries=[_entry("myservice.endpoint", "•••", credentials=True, masked=True)]
    )
    flags = _derive(git_config=git_config)
    creds = [f for f in flags if f.category == "git-config-credentials"]
    assert len(creds) == 1
    assert creds[0].target == "myservice.endpoint"
    assert creds[0].level == PROBLEM


def test_git_no_identity_is_a_single_attention_flag() -> None:
    flags = _derive(git_config=_git_config(identity_present=False))
    no_identity = [f for f in flags if f.category == "git-no-identity"]
    assert len(no_identity) == 1
    assert no_identity[0].section == "git-config"
    assert no_identity[0].target == "identity"
    assert no_identity[0].level == ATTENTION


def test_a_present_identity_raises_no_git_identity_flag() -> None:
    assert [f for f in _derive() if f.category == "git-no-identity"] == []


# ------------------------- Off Sections skip their derivation -------------------------


def test_off_section_raises_no_flags() -> None:
    dirty = _workspace(_repo("~/dev/acme/web", dirty=True))

    # On, the dirty tree flags; Off, its whole derivation is skipped.
    assert [f for f in _derive(workspace=dirty) if f.category == "dirty-tree"]
    assert _derive(workspace=dirty, off={Section.WORKSPACE}) == []


def test_off_docker_skips_the_unreachable_flag() -> None:
    down = DockerSection(daemon_reachable=False)

    assert [f for f in _derive(docker=down) if f.category == "docker-unreachable"]
    assert _derive(docker=down, off={Section.DOCKER}) == []


def test_off_toolchains_leaves_the_claude_shadow_flag() -> None:
    # Drift and shadowing share one cross-item pass, so an Off toolchains must not
    # silence the claude shadow the same pass derives.
    toolchains = _toolchains(
        repo_pins=[
            RepoPin(repo="~/dev/acme/web", version="3.14.4"),
            RepoPin(repo="~/dev/acme/api", version="3.13.13"),
        ]
    )
    claude = _claude(
        skills=[
            Skill(name="layout", origin="user", enabled=True),
            Skill(name="layout", origin="tidy@studio-official", enabled=True),
        ]
    )

    flags = _derive(toolchains=toolchains, claude=claude, off={Section.TOOLCHAINS})
    categories = {f.category for f in flags}

    assert "python-pin-drift" not in categories
    assert "skill-shadow" in categories


# ------------------------- no Status vocabulary -------------------------


def test_no_flag_message_uses_the_status_words() -> None:
    # Exercise every Flag at once, then assert none of the platform Status words
    # (up / stabilising / down) appears in any message or level.
    repo = _repo("~/dev/acme/web", branch="wip", upstream=None, dirty=True, detached_sha=None)
    flags = _derive(
        workspace=_workspace(repo),
        toolchains=_toolchains(
            repo_pins=[
                RepoPin(repo="~/dev/acme/web", version="3.14.4"),
                RepoPin(repo="~/dev/acme/api", version="3.13.13"),
            ]
        ),
        system=_system(Tool(name="ty", version=None, present=False)),
        claude=_claude(
            plugins=[Plugin(name="sketch", marketplace="studio", version="1.0.0", enabled=False)],
            mcp_servers=[
                McpServer(name="cloud-mcp", origin="user", transport="http", needs_auth=True)
            ],
        ),
        homebrew=HomebrewSection(
            present=True,
            formulae=[OutdatedPackage(name="wget", installed="1.21.3", current="1.21.4")],
        ),
        docker=DockerSection(daemon_reachable=False),
    )
    banned = ("up", "stabilising", "down")
    for flag in flags:
        words = flag.message.lower().split()
        assert not any(word in banned for word in words), flag.message
        assert flag.level in (ATTENTION, PROBLEM)


# ------------------------- the CATEGORIES registry -------------------------

STATIC = Path(__file__).parent.parent / "src" / "wkx_ecosystem_localhost" / "static"

# The client's CATEGORY_LABEL map: capture the object literal, then its keys. The
# values carry no braces, so the first "}" closes the map; a colon follows every
# key, so the label strings (which carry none) never match.
_LABEL_BLOCK = re.compile(r"CATEGORY_LABEL\s*=\s*\{(.*?)\}", re.DOTALL)
_LABEL_KEY = re.compile(r'"([a-z0-9-]+)"\s*:')


def _client_category_labels() -> set[str]:
    """The Category ids the board's CATEGORY_LABEL map names, read from app.js."""
    app_js = (STATIC / "app.js").read_text()
    match = _LABEL_BLOCK.search(app_js)
    assert match, "CATEGORY_LABEL map not found in app.js"
    return set(_LABEL_KEY.findall(match.group(1)))


def test_categories_registry_lists_all_nineteen() -> None:
    assert len(CATEGORIES) == 19


def test_registry_carries_the_two_sse_raised_categories() -> None:
    # behind-remote and submodule-tags-behind have no server-side derivation, so
    # they must be named in the registry explicitly or a Mute of them fails.
    assert "behind-remote" in CATEGORIES
    assert "submodule-tags-behind" in CATEGORIES


def test_every_derived_category_is_registered() -> None:
    # No at-rest derivation may raise a Category the registry does not know, or a
    # Mute of it could never validate. Exercise the whole layer, then check.
    repo = _repo("~/dev/acme/web", branch="wip", upstream=None, dirty=True)
    flags = _derive(
        workspace=_workspace(repo),
        toolchains=_toolchains(
            repo_pins=[
                RepoPin(repo="~/dev/acme/web", version="3.14.4"),
                RepoPin(repo="~/dev/acme/api", version="3.13.13"),
            ]
        ),
        system=_system(Tool(name="ty", version=None, present=False)),
        claude=_claude(
            skills=[
                Skill(name="layout", origin="user", enabled=False),
                Skill(name="layout", origin="tidy@studio", enabled=True),
            ],
            plugins=[Plugin(name="sketch", marketplace="studio", version="1.0.0", enabled=False)],
            mcp_servers=[
                McpServer(name="cloud-mcp", origin="user", transport="http", needs_auth=True)
            ],
        ),
        homebrew=HomebrewSection(
            present=True,
            formulae=[OutdatedPackage(name="wget", installed="1.21.3", current="1.21.4")],
        ),
        docker=DockerSection(daemon_reachable=False),
        git_config=_git_config(
            includes=[GitInclude(condition=None, path="~/.gitconfig-missing", exists=False)],
            identity_present=False,
        ),
    )
    assert {flag.category for flag in flags} <= CATEGORIES


def test_client_label_map_and_registry_agree() -> None:
    # The board rolls Flags up by CATEGORY_LABEL; the server validates a Mute
    # against CATEGORIES. If the two drift, a real Category would show a raw id or a
    # Mute of it would be rejected, so they must name exactly the same ids.
    assert _client_category_labels() == set(CATEGORIES)


# ------------------------- mute rule validation -------------------------


def test_mute_defaults_to_empty() -> None:
    settings = Settings(_env_file=None, _config_file=None)

    assert settings.mute == []


def test_mute_accepts_a_known_category_without_a_target() -> None:
    settings = Settings(
        _env_file=None, _config_file=None, mute=[MuteRule(category="brew-outdated")]
    )

    assert settings.mute[0].category == "brew-outdated"
    assert settings.mute[0].target is None


def test_mute_accepts_an_exact_target() -> None:
    settings = Settings(
        _env_file=None,
        _config_file=None,
        mute=[MuteRule(category="dirty-tree", target="~/dev/scratch")],
    )

    assert settings.mute[0].target == "~/dev/scratch"


def test_mute_accepts_the_sse_raised_categories() -> None:
    # The client raises these two, so a Mute of them must still validate.
    settings = Settings(
        _env_file=None,
        _config_file=None,
        mute=[MuteRule(category="behind-remote"), MuteRule(category="submodule-tags-behind")],
    )

    assert {rule.category for rule in settings.mute} == {"behind-remote", "submodule-tags-behind"}


def test_mute_rejects_an_unknown_category_naming_it() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, _config_file=None, mute=[MuteRule(category="brew-outdate")])

    assert "brew-outdate" in str(excinfo.value)


def test_toml_mute_is_an_inline_array_of_rules(tmp_path: Path) -> None:
    path = tmp_path / "wkx-ecosystem-localhost.toml"
    path.write_text(
        'mute = [ { category = "brew-outdated" }, '
        '{ category = "dirty-tree", target = "~/dev/scratch" } ]\n'
    )

    settings = Settings(_env_file=None, _config_file=path)

    assert [(rule.category, rule.target) for rule in settings.mute] == [
        ("brew-outdated", None),
        ("dirty-tree", "~/dev/scratch"),
    ]


def test_env_mute_reads_a_json_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WKX_ECO_LOCAL_MUTE", '[{"category": "brew-outdated"}]')

    settings = Settings(_env_file=None, _config_file=None)

    assert settings.mute == [MuteRule(category="brew-outdated")]


def test_mute_rejects_a_misspelt_rule_key(tmp_path: Path) -> None:
    # A typo'd key must fail fast, not be dropped: a misspelt `targett` would leave
    # target None and silently widen the rule from one item to the whole category.
    path = tmp_path / "wkx-ecosystem-localhost.toml"
    path.write_text('mute = [ { category = "dirty-tree", targett = "~/dev/scratch" } ]\n')

    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, _config_file=path)

    assert "targett" in str(excinfo.value)
