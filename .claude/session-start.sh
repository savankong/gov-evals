#!/usr/bin/env bash
# Prepare a fresh checkout so tests and typechecks can run immediately.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 0

log() { printf '%s\n' "$*" >&2; }

if [ ! -d .venv ]; then
  python3 -m venv .venv >/dev/null 2>&1 || { log "Could not create the virtualenv."; exit 0; }
fi

.venv/bin/pip install --quiet --upgrade pip >/dev/null 2>&1
.venv/bin/pip install --quiet -e "apps/api[dev]" >/dev/null 2>&1 \
  && log "API installed. Run: cd apps/api && ../../.venv/bin/pytest -q" \
  || log "API install failed; check network access to the package index."
.venv/bin/pip install --quiet -e "packages/sdk" >/dev/null 2>&1

if [ ! -d apps/web/node_modules ]; then
  (cd apps/web && npm install --silent >/dev/null 2>&1) \
    && log "Web dependencies installed." \
    || log "npm install failed; the web UI will not build until it succeeds."
fi

exit 0
