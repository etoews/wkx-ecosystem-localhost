#!/usr/bin/env bash
# Driver for the WKX Ecosystem localhost board.
#
# Launches the real app on loopback, smoke-tests every API endpoint (JSON and
# SSE), and captures a screenshot of the rendered board with headless Chrome.
#
# The board inventories THIS machine (its repos, git config, Claude environment,
# Homebrew, Docker). The screenshot therefore contains real, machine-specific
# data: it is written outside the repo by default and must never be committed to
# this public, machine-neutral repository.
#
# Usage:  bash smoke.sh [PORT] [SCREENSHOT_PATH]
#   PORT             loopback port to bind (default 8787)
#   SCREENSHOT_PATH  where to write the board PNG (default $TMPDIR/wkx-board.png)
set -uo pipefail

PORT="${1:-8787}"
SHOT="${2:-${TMPDIR:-/tmp}/wkx-board.png}"
BASE="http://127.0.0.1:${PORT}"
LOG="${TMPDIR:-/tmp}/wkx-serve.log"
BODY="${TMPDIR:-/tmp}/wkx-body.json"

# The skill lives at <repo>/.claude/skills/run-wkx-ecosystem-localhost/; walk up
# three levels to the repo root so this runs from anywhere.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT"

fail=0

echo "==> launching board on ${BASE}  (repo: ${REPO_ROOT})"
uv run wkx-ecosystem-localhost serve --port "$PORT" >"$LOG" 2>&1 &
SERVER=$!
trap 'kill "$SERVER" 2>/dev/null' EXIT

code=""
for _ in $(seq 1 60); do
  code="$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/api/health" 2>/dev/null || true)"
  [ "$code" = "200" ] && break
  sleep 0.25
done
if [ "$code" != "200" ]; then
  echo "!! server never became healthy; last log lines:"; tail -20 "$LOG"; exit 1
fi
echo "==> healthy"

check() { # <path>
  local path="$1" c
  c="$(curl -s -o "$BODY" -w '%{http_code}' "${BASE}${path}")"
  if [ "$c" = "200" ] && jq -e . "$BODY" >/dev/null 2>&1; then
    printf '  ok    %-20s %s\n' "$path" \
      "$(jq -c 'if type=="object" then (keys|join(",")) else "list("+(length|tostring)+")" end' "$BODY" 2>/dev/null | cut -c1-58)"
  else
    printf '  FAIL  %-20s http=%s\n' "$path" "$c"; fail=1
  fi
}

echo "==> JSON endpoints"
for p in /api/health /api/workspace /api/submodules /api/toolchains \
         /api/system /api/claude /api/homebrew /api/docker /api/flags /api/config; do
  check "$p"
done

sse() { # <path>  -- confirm the endpoint emits well-formed SSE frames
  local path="$1" out
  out="$(curl -sN --max-time 8 "${BASE}${path}" 2>/dev/null)"
  if printf '%s' "$out" | grep -qE '^(data|event):'; then
    printf '  ok    %-20s frames=%s\n' "$path" "$(printf '%s' "$out" | grep -cE '^data:')"
  else
    printf '  FAIL  %-20s (no SSE frames in 8s)\n' "$path"; fail=1
  fi
}

echo "==> SSE endpoints  (a background git fetch runs; may take a few seconds)"
sse /api/workspace/fetch
sse /api/submodules/probe

echo "==> screenshot -> ${SHOT}  (contains real machine data; do not commit)"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if [ -x "$CHROME" ]; then
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars \
    --window-size=1440,2400 --virtual-time-budget=8000 \
    --screenshot="$SHOT" "${BASE}/" >/dev/null 2>&1
  if [ -s "$SHOT" ]; then
    echo "  wrote $(du -h "$SHOT" | cut -f1 | tr -d ' ') to ${SHOT}"
  else
    echo "  !! screenshot was empty"; fail=1
  fi
else
  echo "  !! Google Chrome not found at ${CHROME}; skipping screenshot"; fail=1
fi

echo "==> done ($([ "$fail" = 0 ] && echo PASS || echo FAIL)); server stops on exit"
exit "$fail"
