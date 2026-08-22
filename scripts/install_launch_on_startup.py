#!/usr/bin/env python3
"""Install a macOS launchd LaunchAgent that runs the board at login with reload.

The one always-on instance is also the development instance: a change to the
package source restarts it and the new code is served.

This installer is machine-neutral. It fills the committed plist template with
values found on the machine it runs on, writes the result to
``~/Library/LaunchAgents`` (outside this repository), validates it, and loads
it. The rendered plist holds real, machine-specific paths and is never committed
to this public, machine-neutral repository.

Run it with::

    uv run scripts/install_launch_on_startup.py

Each option falls back to an environment variable, then to a computed default.
"""

from __future__ import annotations

import argparse
import contextlib
import getpass
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from string import Template

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = REPO_ROOT / "scripts" / "wkx-ecosystem-localhost.plist.template"


def render_plist(template: str, values: dict[str, str]) -> str:
    """Return the template with every ``${TOKEN}`` replaced from ``values``.

    Raise ``ValueError`` if the template names a placeholder that ``values`` does
    not supply, so a missing or misspelled key fails loudly instead of writing a
    broken plist.
    """
    try:
        return Template(template).substitute(values)
    except KeyError as missing:
        raise ValueError(f"template placeholder {missing} has no value") from missing


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line. Options are documented with their env fallbacks."""
    parser = argparse.ArgumentParser(
        description="Install the launchd LaunchAgent that runs the board at login.",
    )
    parser.add_argument("--port", help="Loopback port to bind (env PORT; default 8787).")
    parser.add_argument("--label", help="LaunchAgent label (env LABEL).")
    parser.add_argument(
        "--shell",
        help="Login shell to run the agent (env SHELL_BIN; default /bin/zsh).",
    )
    parser.add_argument(
        "--uv",
        help="Path to the uv executable (env UV_BIN; default: found on PATH).",
    )
    parser.add_argument(
        "--log",
        help="Combined stdout/stderr log path (env LOG_PATH).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the rendered plist and exit; do not write or load it.",
    )
    return parser.parse_args(argv)


def _pick(cli_value: str | None, env_name: str, default: str) -> str:
    """Resolve a value from the CLI, then the environment, then a default."""
    if cli_value is not None:
        return cli_value
    return os.environ.get(env_name) or default


def _launchctl(*args: str) -> subprocess.CompletedProcess[str]:
    """Run a launchctl subcommand, capturing output and never raising."""
    return subprocess.run(["launchctl", *args], capture_output=True, text=True, check=False)


def _loaded(service: str) -> bool:
    """Return whether launchd currently knows the service."""
    return _launchctl("print", service).returncode == 0


def _reload(domain: str, service: str, plist_path: Path) -> None:
    """Boot the old instance out, wait for it, then bootstrap the new plist.

    bootout is asynchronous, so bootstrapping the same label straight away races
    the teardown and fails with error 5. Wait for the unload, then bootstrap with
    a short retry in case it is still settling.
    """
    _launchctl("bootout", service)
    for _ in range(20):
        if not _loaded(service):
            break
        time.sleep(0.5)

    for attempt in range(1, 4):
        result = _launchctl("bootstrap", domain, str(plist_path))
        if result.returncode == 0:
            return
        if attempt == 3:
            sys.exit(f"error: launchctl bootstrap failed for {service}: {result.stderr.strip()}")
        time.sleep(1)


def _wait_for_health(url: str, timeout: int = 30) -> bool:
    """Poll the health endpoint until it answers 200 or the timeout passes."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with (
            contextlib.suppress(urllib.error.URLError, OSError),
            urllib.request.urlopen(url, timeout=2) as response,
        ):
            if response.status == 200:
                return True
        time.sleep(1)
    return False


def main(argv: list[str] | None = None) -> None:
    """Render, validate, and load the LaunchAgent, then report how to manage it."""
    args = parse_args(argv)

    if not TEMPLATE.is_file():
        sys.exit(f"error: template not found at {TEMPLATE}")

    port = _pick(args.port, "PORT", "8787")
    if not port.isdigit():
        sys.exit(f"error: --port must be an integer, got {port!r}")
    label = _pick(args.label, "LABEL", f"dev.{getpass.getuser()}.wkx-ecosystem-localhost")
    shell = _pick(args.shell, "SHELL_BIN", "/bin/zsh")
    default_log = str(Path.home() / "Library" / "Logs" / "wkx-ecosystem-localhost.log")
    log_path = _pick(args.log, "LOG_PATH", default_log)
    uv_bin = args.uv or os.environ.get("UV_BIN") or shutil.which("uv")
    if not uv_bin:
        sys.exit("error: uv not found on PATH; install uv or pass --uv /abs/path/to/uv")

    values = {
        "LABEL": label,
        "SHELL": shell,
        "UV_BIN": uv_bin,
        "PORT": port,
        "WORKING_DIR": str(REPO_ROOT),
        "LOG_PATH": log_path,
    }
    plist_text = render_plist(TEMPLATE.read_text(), values)

    if args.dry_run:
        print(plist_text)
        return

    if sys.platform != "darwin":
        sys.exit("error: this installer targets macOS launchd; use --dry-run elsewhere")
    if not (Path(shell).exists() and os.access(shell, os.X_OK)):
        sys.exit(f"error: login shell {shell} is not executable; pass --shell /bin/zsh")

    launch_agents = Path.home() / "Library" / "LaunchAgents"
    launch_agents.mkdir(parents=True, exist_ok=True)
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)

    plist_path = launch_agents / f"{label}.plist"
    plist_path.write_text(plist_text)

    lint = subprocess.run(
        ["plutil", "-lint", str(plist_path)], capture_output=True, text=True, check=False
    )
    print(lint.stdout.strip() or f"{plist_path}: OK")
    if lint.returncode != 0:
        sys.exit(lint.stderr.strip() or "error: plutil -lint failed")

    domain = f"gui/{os.getuid()}"
    service = f"{domain}/{label}"
    _reload(domain, service, plist_path)

    url = f"http://127.0.0.1:{port}/"
    print(f"waiting for the board on 127.0.0.1:{port} ...", end=" ", flush=True)
    healthy = _wait_for_health(f"{url}api/health")
    print("ok" if healthy else f"no answer yet; check the log at {log_path}")

    print(
        f"\ninstalled and loaded: {label}\n"
        f"  plist:  {plist_path}\n"
        f"  log:    {log_path}\n"
        f"  url:    {url}\n\n"
        "manage:\n"
        f"  status:  launchctl print {service}\n"
        f"  restart: launchctl kickstart -k {service}   # after a dependency change\n"
        f"  stop:    launchctl bootout {service}"
    )


if __name__ == "__main__":
    main()
