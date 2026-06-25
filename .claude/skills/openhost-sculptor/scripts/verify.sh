#!/bin/sh
# Verify a deployed Sculptor OpenHost app: right code live, serving, clean boot.
# All over the CLI / HTTP — no SSH.
#
# Usage: verify.sh <host>     e.g. verify.sh sculptor.<your-zone>
# <host> is your instance's public host — the one per-machine value. See SKILL.md
# ("Config") for where it lives (.sculptor/.env) and how to obtain it.
set -eu
APP=sculptor
HOST=${1:?usage: verify.sh <host> (e.g. sculptor.<your-zone>); see SKILL.md "Config"}

echo "== app status (expect 'running') =="
# `oh app status`/`logs` address the app by name. An instance older than the CLI
# keys these endpoints on an opaque app_id instead and rejects the name with
# "Invalid app_id" — see SKILL.md "Gotchas" for the version skew and how to fetch
# the id. Don't let that abort the rest of the checks (set -eu).
oh app status "$APP" || echo "  (status failed — if 'Invalid app_id', your instance predates name-based status; see SKILL.md Gotchas)"

echo
echo "== serving: https://$HOST/ =="
code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://$HOST/" || echo "000")
case "$code" in
    302) echo "  HTTP $code — healthy (OpenHost SSO login redirect, not an error)" ;;
    200) echo "  HTTP $code — serving" ;;
    *) echo "  HTTP $code — NOT healthy (still building, crashed, or failed to bind)" ;;
esac

echo
echo "== boot markers =="
logs=$(oh app logs "$APP" 2>/dev/null || true)
printf '%s\n' "$logs" | grep -q "Uvicorn running on" &&
    echo "  ok  Uvicorn running" || echo "  --  'Uvicorn running' not found yet"
printf '%s\n' "$logs" | grep -q "Application startup complete" &&
    echo "  ok  Application startup complete" || echo "  --  'Application startup complete' not found yet"
