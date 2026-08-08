"""The footprint Collector: how much disk the dev workspace and Docker consume.

For each discovered repo it measures the two heavyweight, regenerable directories,
its ``.venv`` and its ``node_modules``, with ``du -sk`` through the ``Machine``
seam, and pairs that with the total and reclaimable Docker disk. A directory that
is absent (``du`` exits non-zero) is a fact, never an error: it simply does not
count toward the repo, and a repo with neither is left out entirely. The KiB
reader is pure, so its edge cases pin directly against synthetic fixtures. Facts
only; anomaly judgement is the separate M6 Flag layer.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

from wkx_ecosystem_localhost.collectors.docker import collect_docker, humanise_size
from wkx_ecosystem_localhost.machine import Machine
from wkx_ecosystem_localhost.models import FootprintSection, RepoFootprint
from wkx_ecosystem_localhost.redaction import relativise

logger = logging.getLogger(__name__)

# The size probe. ``du -sk`` prints a single ``<KiB>\t<path>`` line for a
# directory that exists and exits non-zero for one that does not. ``-k`` fixes the
# block size at 1024 bytes, so the reported count is KiB regardless of platform
# defaults; the full argv is this prefix followed by the path to measure.
DU_ARGV_PREFIX = ("du", "-sk")

# ``du`` blocks are 1024-byte (KiB) units under ``-k``, so bytes are KiB times this.
_KIB = 1024

# The two regenerable directories measured per repo, in board order.
_VENV_DIR = ".venv"
_NODE_MODULES_DIR = "node_modules"

# Per-probe wall-clock ceiling. Generous because ``du`` walks a whole tree, tight
# enough that one enormous directory degrades a single figure, not the board.
PROBE_TIMEOUT_S = 30.0


def parse_du_kib(stdout: str) -> int | None:
    """Read the KiB count from a ``du -sk`` line.

    ``du -sk`` prints ``<KiB>\\t<path>``; only the leading integer token is read,
    so the trailing path is ignored. Output whose first whitespace-separated token
    is not an integer (empty, blank, or shapeless) yields None, degrading a single
    figure rather than raising.

    Args:
        stdout: The stdout of ``du -sk <path>``.

    Returns:
        The size in KiB, or None when the leading token is not an integer.
    """
    tokens = stdout.split()
    if not tokens:
        return None
    try:
        return int(tokens[0])
    except ValueError:
        return None


def _du_bytes(machine: Machine, path: Path, *, timeout: float) -> int | None:
    """Measure ``path`` with ``du -sk`` through the seam, in bytes, or None if absent.

    A non-zero exit (the directory does not exist) or unreadable output is a fact,
    reported as None, so an absent ``.venv`` or ``node_modules`` degrades to "not
    present" rather than raising.
    """
    result = machine.run((*DU_ARGV_PREFIX, str(path)), timeout=timeout)
    if not result.ok:
        return None
    kib = parse_du_kib(result.stdout)
    return None if kib is None else kib * _KIB


def _repo_footprint(
    machine: Machine, repo_path: Path, *, home: Path, timeout: float
) -> RepoFootprint | None:
    """Measure one repo's regenerable directories, or None when it has neither.

    Probes the repo's ``.venv`` and ``node_modules``; a repo carrying neither
    contributes nothing to the Section and is dropped. The two sizes are humanised
    for display while the raw byte total is kept so the Section can rank repos.
    """
    venv_bytes = _du_bytes(machine, repo_path / _VENV_DIR, timeout=timeout)
    node_bytes = _du_bytes(machine, repo_path / _NODE_MODULES_DIR, timeout=timeout)
    if venv_bytes is None and node_bytes is None:
        return None
    total_bytes = (venv_bytes or 0) + (node_bytes or 0)
    return RepoFootprint(
        name=repo_path.name,
        path=relativise(repo_path, home),
        venv=humanise_size(venv_bytes) if venv_bytes is not None else None,
        node_modules=humanise_size(node_bytes) if node_bytes is not None else None,
        total=humanise_size(total_bytes),
        total_bytes=total_bytes,
    )


def collect_footprint(
    machine: Machine,
    repo_paths: Sequence[Path],
    *,
    home: Path,
    timeout: float = PROBE_TIMEOUT_S,
) -> FootprintSection:
    """Collect the footprint Section: per-repo disk usage plus the Docker disk.

    A pure Collector over the seam. Every ``du`` probe and the Docker probe reach
    the host only through ``machine``, so the whole Section is exercised in tests
    against a fake. Repos with neither a ``.venv`` nor a ``node_modules`` are left
    out, and the rest are ranked by true bytes so the board reads biggest-first. No
    judgement is applied: the sizes are plain facts for the M6 Flag layer, which
    derives nothing from footprint.

    Args:
        machine: The seam every probe runs through.
        repo_paths: The discovered repos to measure, in any order.
        home: Home directory, for relativising displayed paths.
        timeout: Per-``du`` wall-clock ceiling in seconds.

    Returns:
        The Section model: the ranked repo footprints with their total, and the
        embedded total and reclaimable Docker disk.
    """
    repos = [
        footprint
        for path in repo_paths
        if (footprint := _repo_footprint(machine, path, home=home, timeout=timeout)) is not None
    ]
    repos.sort(key=lambda repo: repo.total_bytes, reverse=True)
    docker = collect_docker(machine)
    return FootprintSection(
        repos=repos,
        repos_total=humanise_size(sum(repo.total_bytes for repo in repos)),
        docker_reachable=docker.daemon_reachable,
        docker_total=docker.total_disk,
        docker_reclaimable=docker.reclaimable,
    )
