"""The git-config Collector: the whole global gitconfig chain, targeted-redacted.

One read-only probe through the ``Machine`` seam: ``git config --global --list
--show-origin --includes`` lists every key in the global chain, each tagged with
the file it came from and with any ``include`` directives already expanded. Unlike
the M1 per-repo view, which is a deny-by-default whitelist, this inventory shows
every key and masks only the secret-bearing families, per ADR 0001. The line
splitter, the per-value redactor, and the multi-valued recogniser are pure, so
their edge cases pin directly against synthetic fixtures. Facts only; anomaly
judgement is the separate M6 Flag layer.
"""

from __future__ import annotations

import logging
from pathlib import Path

from wkx_ecosystem_localhost.machine import Machine
from wkx_ecosystem_localhost.models import GitConfigEntry, GitConfigSection, GitInclude
from wkx_ecosystem_localhost.redaction import relativise, relativise_text, strip_credentials

logger = logging.getLogger(__name__)

# The single probe this Collector runs. ``--show-origin`` tags each key with the
# file it was read from, ``--includes`` follows include directives so keys pulled
# in from another file appear with that file as their origin.
GITCONFIG_ARGV = ("git", "config", "--global", "--list", "--show-origin", "--includes")

# Per-probe wall-clock ceiling. Generous for a local config read, tight enough
# that a wedged git degrades this one Section rather than hanging the board.
PROBE_TIMEOUT_S = 5.0

# The mask shown in place of a secret-bearing value.
_MASKED = "•••"

# The ``file:`` prefix ``--show-origin`` puts before each origin path.
_ORIGIN_FILE_PREFIX = "file:"

# Substrings that mark a key name as secret-bearing wherever they appear (ADR 0001).
_SECRET_SUBSTRINGS = ("token", "password", "secret", "authorization")

# The final dotted component of a legitimately multi-valued key. A key ending in
# one of these holds a list, not a single setting, so two differing values are the
# design, never a conflict to flag.
_MULTIVAR_FINALS = frozenset({"insteadof", "pushinsteadof", "fetch", "push"})


def parse_git_config(stdout: str) -> list[dict[str, str]]:
    """Split ``--show-origin`` output into one ``{key, value, origin_path}`` per line.

    Each line is ``file:<abs-path>\\t<key>=<value>``: the separator before the
    key/value pair is a tab, so the origin is taken up to the first tab (with the
    ``file:`` prefix stripped) and the key/value split on the first ``=`` so a value
    carrying its own ``=`` rides along intact. A line with no tab or no ``=`` is
    skipped rather than raising, so unexpected shape degrades a line, not the read.

    Args:
        stdout: The stdout of ``git config --global --list --show-origin --includes``.

    Returns:
        One mapping per readable line, in input order, preserving duplicate keys.
    """
    entries: list[dict[str, str]] = []
    for line in stdout.splitlines():
        origin_raw, tab, kv = line.partition("\t")
        if not tab:
            continue
        key, sep, value = kv.partition("=")
        if not sep:
            continue
        origin_path = origin_raw.removeprefix(_ORIGIN_FILE_PREFIX)
        entries.append({"key": key, "value": value, "origin_path": origin_path})
    return entries


def redact_value(key: str, value: str, home: Path) -> tuple[str, bool]:
    """Decide a value's display form and whether it is masked, per ADR 0001.

    A secret-bearing key is masked whole: one whose name ends ``.extraheader``, one
    under ``credential.*``, or one whose name contains token, password, secret, or
    authorization. Every other value is shown, with any embedded URL credentials
    stripped and any home path in it rewritten to ``~`` so a screenshot leaks
    neither a token nor a username. ``user.email`` is not a secret family, so it is
    shown unmasked on this loopback-only board.

    Args:
        key: The git-normalised config key.
        value: Its raw value.
        home: Home directory, for relativising a path embedded in the value.

    Returns:
        A ``(display, masked)`` pair: the string to show and whether it was masked.
    """
    lower = key.lower()
    if (
        lower.endswith(".extraheader")
        or lower.startswith("credential.")
        or any(token in lower for token in _SECRET_SUBSTRINGS)
    ):
        return _MASKED, True
    return relativise_text(strip_credentials(value), home), False


def is_multivar(key: str) -> bool:
    """True when ``key`` names a legitimately multi-valued family.

    A key whose final dotted component (lowercased) is ``insteadof``,
    ``pushinsteadof``, ``fetch``, or ``push`` holds a list of values by design, so
    it is excluded from conflict and shadow detection: two differing values there
    are expected, not an anomaly.
    """
    return key.rsplit(".", 1)[-1].lower() in _MULTIVAR_FINALS


def _resolve_include_target(target: str, origin_path: str, home: Path) -> Path:
    """Resolve an include's target to an absolute path.

    A leading ``~/`` expands against ``home``; a relative target resolves against
    the directory of the file the directive was read from; an absolute target is
    taken as-is. This mirrors how git itself locates an included file.
    """
    if target.startswith("~/"):
        return home / target[2:]
    candidate = Path(target)
    if candidate.is_absolute():
        return candidate
    return Path(origin_path).parent / target


def _build_include(
    machine: Machine, key: str, value: str, origin_path: str, *, home: Path
) -> GitInclude | None:
    """Build a ``GitInclude`` from an include directive, or None for a normal key.

    A plain ``include.path`` has no condition; an ``includeIf`` key of the form
    ``includeif.<condition>.path`` carries its condition between the prefix and the
    ``.path`` suffix (the condition may itself hold dots and colons, so it is peeled
    off by prefix/suffix, not split). The target is resolved and its existence
    checked through the seam so a directive pointing at a missing file shows broken.
    """
    if key == "include.path":
        condition: str | None = None
    elif key.startswith("includeif.") and key.endswith(".path"):
        condition = key.removeprefix("includeif.").removesuffix(".path")
    else:
        return None
    resolved = _resolve_include_target(value, origin_path, home)
    return GitInclude(
        condition=condition,
        path=relativise(resolved, home),
        exists=machine.read_file(resolved) is not None,
    )


def _shadowed_entries(raw_entries: list[tuple[str, str, str]]) -> list[bool]:
    """Mark each single-valued entry a later entry overrides with a different value.

    git is last-wins for a single-valued key, so an earlier entry set to a value a
    later entry changes has no effect: it is shadowed. Multi-valued keys hold a list
    by design and so are never shadowed. Values are compared raw so a difference is
    real even when both display forms are masked.
    """
    shadowed: list[bool] = []
    for index, (key, raw, _origin) in enumerate(raw_entries):
        is_shadowed = not is_multivar(key) and any(
            later_key == key and later_raw != raw
            for later_key, later_raw, _ in raw_entries[index + 1 :]
        )
        shadowed.append(is_shadowed)
    return shadowed


def collect_git_config(
    machine: Machine, *, home: Path, timeout: float = PROBE_TIMEOUT_S
) -> GitConfigSection:
    """Collect the git-config Section: the whole global gitconfig chain as facts.

    A pure Collector over the seam. The one probe reaches the host only through
    ``machine``, so the whole Section is exercised in tests against a fake. A probe
    that cannot be read (git absent, or no global config) is a fact: the Section
    degrades to empty with no identity, never an error. Every key is shown with
    targeted redaction (ADR 0001); include directives are lifted out of the entry
    list, their targets resolved and existence-checked. No judgement is applied; the
    conflict, broken-include, credential, and no-identity anomalies are left for the
    M6 Flag layer to interpret.

    Args:
        machine: The seam the probe and the include reads run through.
        home: Home directory, for relativising origins, paths, and values.
        timeout: Per-probe wall-clock ceiling in seconds.

    Returns:
        The Section model: the config entries, the include directives, and whether a
        committing identity is present.
    """
    result = machine.run(GITCONFIG_ARGV, timeout=timeout)
    if not result.ok:
        return GitConfigSection(entries=[], includes=[], identity_present=False)

    raw_entries: list[tuple[str, str, str]] = []
    includes: list[GitInclude] = []
    for item in parse_git_config(result.stdout):
        key, value, origin_path = item["key"], item["value"], item["origin_path"]
        include = _build_include(machine, key, value, origin_path, home=home)
        if include is not None:
            includes.append(include)
            continue
        raw_entries.append((key, value, origin_path))

    entries: list[GitConfigEntry] = []
    for (key, raw, origin_path), is_shadowed in zip(
        raw_entries, _shadowed_entries(raw_entries), strict=True
    ):
        display, masked = redact_value(key, raw, home)
        # A credential embedded in a URL value is stripped, not masked whole
        # (ADR 0001): the endpoint stays visible for the inventory, the userinfo is
        # dropped by redact_value, and the red credentials Flag warns. A
        # secret-bearing key is already masked by redact_value above.
        credentials = strip_credentials(raw) != raw
        entries.append(
            GitConfigEntry(
                key=key,
                value=display,
                origin=relativise(Path(origin_path), home),
                masked=masked,
                shadowed=is_shadowed,
                credentials=credentials,
            )
        )

    identity_present = any(entry.key == "user.email" for entry in entries)
    return GitConfigSection(entries=entries, includes=includes, identity_present=identity_present)
