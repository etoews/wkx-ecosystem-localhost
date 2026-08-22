#!/usr/bin/env bash
# Install a macOS launchd LaunchAgent that runs the board at login with live
# reload. The one always-on instance is also the development instance: a change
# to the package source restarts it and the new code is served.
#
# This script is machine-neutral. It fills the committed plist template with
# values found on the machine it runs on, writes the result to
# ~/Library/LaunchAgents (outside this repository), validates it, and loads it.
# The rendered plist holds real, machine-specific paths and must never be
# committed to this public, machine-neutral repository.
#
# Usage:  scripts/install-launch-on-startup.sh
#
# Override any value with an environment variable:
#   PORT       loopback port to bind (default 8787)
#   LABEL      LaunchAgent label     (default dev.<user>.wkx-ecosystem-localhost)
#   UV_BIN     absolute path to uv   (default: resolved from PATH)
#   SHELL_BIN  login shell to run    (default /bin/zsh)
#   LOG_PATH   combined stdout/stderr log
#              (default ~/Library/Logs/wkx-ecosystem-localhost.log)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="${REPO_ROOT}/scripts/wkx-ecosystem-localhost.plist.template"

PORT="${PORT:-8787}"
LABEL="${LABEL:-dev.$(id -un).wkx-ecosystem-localhost}"
SHELL_BIN="${SHELL_BIN:-/bin/zsh}"
LOG_PATH="${LOG_PATH:-${HOME}/Library/Logs/wkx-ecosystem-localhost.log}"
UV_BIN="${UV_BIN:-$(command -v uv || true)}"

PLIST_DIR="${HOME}/Library/LaunchAgents"
PLIST="${PLIST_DIR}/${LABEL}.plist"
DOMAIN="gui/$(id -u)"

# Preflight.
if [ ! -f "${TEMPLATE}" ]; then
    echo "error: template not found at ${TEMPLATE}" >&2
    exit 1
fi
if [ -z "${UV_BIN}" ]; then
    echo "error: uv not found on PATH. Install uv, or set UV_BIN=/abs/path/to/uv" >&2
    exit 1
fi
if [ ! -x "${SHELL_BIN}" ]; then
    echo "error: login shell ${SHELL_BIN} is not executable. Set SHELL_BIN=/bin/zsh" >&2
    exit 1
fi

mkdir -p "${PLIST_DIR}" "$(dirname "${LOG_PATH}")"

# Render the template. '|' is the sed delimiter and does not occur in these paths.
sed \
    -e "s|@@LABEL@@|${LABEL}|g" \
    -e "s|@@SHELL@@|${SHELL_BIN}|g" \
    -e "s|@@UV_BIN@@|${UV_BIN}|g" \
    -e "s|@@PORT@@|${PORT}|g" \
    -e "s|@@WORKING_DIR@@|${REPO_ROOT}|g" \
    -e "s|@@LOG_PATH@@|${LOG_PATH}|g" \
    "${TEMPLATE}" >"${PLIST}"

plutil -lint "${PLIST}"

# Reload: remove any earlier instance of this label, then load the new one.
# bootout is asynchronous, so wait for the old service to unload before
# bootstrapping the same label; otherwise bootstrap races it and fails with 5.
launchctl bootout "${DOMAIN}/${LABEL}" 2>/dev/null || true
for _ in $(seq 1 20); do
    launchctl print "${DOMAIN}/${LABEL}" >/dev/null 2>&1 || break
    sleep 0.5
done

# Bootstrap, with a short retry in case the unload is still settling.
for attempt in 1 2 3; do
    if launchctl bootstrap "${DOMAIN}" "${PLIST}" 2>/dev/null; then
        break
    fi
    if [ "${attempt}" = "3" ]; then
        echo "error: launchctl bootstrap failed for ${DOMAIN}/${LABEL}" >&2
        echo "       try: launchctl bootout ${DOMAIN}/${LABEL} ; then re-run" >&2
        exit 1
    fi
    sleep 1
done

# Verify the board answers (best effort).
printf 'waiting for the board on 127.0.0.1:%s ' "${PORT}"
ok=""
for _ in $(seq 1 30); do
    if curl -fs -o /dev/null "http://127.0.0.1:${PORT}/api/health"; then
        ok="yes"
        break
    fi
    printf '.'
    sleep 1
done
if [ -n "${ok}" ]; then
    echo " ok"
else
    echo " no answer yet; check the log at ${LOG_PATH}"
fi

cat <<EOF

installed and loaded: ${LABEL}
  plist:  ${PLIST}
  log:    ${LOG_PATH}
  url:    http://127.0.0.1:${PORT}/

manage:
  status:  launchctl print ${DOMAIN}/${LABEL}
  restart: launchctl kickstart -k ${DOMAIN}/${LABEL}   # after a dependency change
  stop:    launchctl bootout ${DOMAIN}/${LABEL}
EOF
