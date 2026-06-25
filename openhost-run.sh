#!/bin/sh
# Entrypoint for the OpenHost dev image (branch: maciek/oh-proxy-sidecar).
#
# Runs the Sculptor backend on 127.0.0.1:5051 behind an nginx front on :5050 (the
# port OpenHost proxies to). nginx adds a /proxy/<port>/ reverse-proxy to localhost
# dev servers for mobile live-preview. See openhost-nginx.conf for the routing.
set -eu

# Persist into whichever app-data dir OpenHost granted THIS app
# (/data/app_data/<app-name>, injected as OPENHOST_APP_DATA_DIR), so the same
# image works for the prod 'sculptor' app and any separate dev app without
# hard-coding the name. Falls back to the Dockerfile ENV defaults off-OpenHost.
if [ -n "${OPENHOST_APP_DATA_DIR:-}" ]; then
    export SCULPTOR_FOLDER="$OPENHOST_APP_DATA_DIR"
    export CLAUDE_CONFIG_DIR="$OPENHOST_APP_DATA_DIR/claude"
    export GH_CONFIG_DIR="$OPENHOST_APP_DATA_DIR/gh"
fi
mkdir -p "$SCULPTOR_FOLDER" "$CLAUDE_CONFIG_DIR" "$GH_CONFIG_DIR" /tmp/nginx

# Backend behind nginx (SCULPTOR_API_PORT=5051 is set in the Dockerfile).
/app/.venv/bin/python -m sculptor.cli.main --no-open-browser /workspace &
backend_pid=$!

# If nginx exits, take the backend down too (and vice-versa on container stop).
trap 'kill "$backend_pid" 2>/dev/null || true' EXIT INT TERM

exec nginx -c /app/openhost-nginx.conf -g 'daemon off;'
