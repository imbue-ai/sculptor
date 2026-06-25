#!/bin/sh
# Entrypoint for the OpenHost Sculptor image.
#
# Runs the Sculptor backend on 127.0.0.1:5051 behind an nginx front on :5050 (the
# port OpenHost proxies to). nginx adds a /proxy/<port>/ reverse-proxy to localhost
# dev servers for mobile live-preview. See openhost-nginx.conf for the routing.
set -eu

# Persist into whichever app-data dir OpenHost granted THIS app
# (/data/app_data/<app-name>, injected as OPENHOST_APP_DATA_DIR), so the same
# image works for any app name without hard-coding it. Falls back to the
# Dockerfile ENV defaults off-OpenHost.
if [ -n "${OPENHOST_APP_DATA_DIR:-}" ]; then
    export SCULPTOR_FOLDER="$OPENHOST_APP_DATA_DIR"
    export CLAUDE_CONFIG_DIR="$OPENHOST_APP_DATA_DIR/claude"
    export GH_CONFIG_DIR="$OPENHOST_APP_DATA_DIR/gh"
fi
mkdir -p "$SCULPTOR_FOLDER" "$CLAUDE_CONFIG_DIR" "$GH_CONFIG_DIR" /tmp/nginx

# Re-establish the gh credential helper + a git identity on every boot: /home is
# wiped on each rebuild, so ~/.gitconfig is lost even though the gh TOKEN persists
# under GH_CONFIG_DIR. Identity is DERIVED from whoever is signed in to gh (login
# + GitHub noreply email) — never hard-coded — so commits attribute to the actual
# signed-in user, and a deploy by someone else attributes to them. Best-effort:
# must NOT fail the boot if gh is absent or unauthenticated (a fresh instance
# before the in-app GitHub sign-in).
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    gh auth setup-git || true
    _gh_login=$(gh api user --jq '.login' 2>/dev/null || true)
    _gh_id=$(gh api user --jq '.id' 2>/dev/null || true)
    if [ -n "${_gh_login:-}" ]; then
        git config --global user.name "$_gh_login" || true
        git config --global user.email "${_gh_id:+${_gh_id}+}${_gh_login}@users.noreply.github.com" || true
    fi
fi

# Backend behind nginx (SCULPTOR_API_PORT=5051 is set in the Dockerfile).
/app/.venv/bin/python -m sculptor.cli.main --no-open-browser /workspace &
backend_pid=$!

# If nginx exits, take the backend down too (and vice-versa on container stop).
trap 'kill "$backend_pid" 2>/dev/null || true' EXIT INT TERM

exec nginx -c /app/openhost-nginx.conf -g 'daemon off;'
