#!/usr/bin/env bash
# Launch a Vite dev preview reachable from your phone at
#
#     https://<this-app-host>/proxy/<port>/
#
# through the OpenHost nginx /proxy front (see ../../openhost-nginx.conf). Only
# the owner's SSO'd session can reach that URL — nothing is made public.
#
# How it fits together:
#   - Vite binds 127.0.0.1:<port>; nginx reaches it on loopback and forwards the
#     /proxy/<port>/ path through UNSTRIPPED.
#   - SCULPTOR_PROXY_BASE makes Vite serve under base=/proxy/<port>/ and point its
#     HMR client back through the TLS edge (wss, :443) — see vite.base.config.ts.
#   - The app's /api + /ws calls are same-origin ABSOLUTE (the web build compiles
#     API base to ""), so they bypass this Vite and hit the SHARED backend via
#     nginx. No per-preview backend is needed (and full-stack previews are parked
#     on the cookie-scoping question — see the dev-preview doc).
set -euo pipefail

port="${1:-}"
case "$port" in
  5[1-9][0-9][0-9][0-9]) ;;   # 51000-59999, the nginx preview band
  *) echo "usage: $(basename "$0") <port in 51000-59999>" >&2; exit 1 ;;
esac

cd "$(dirname "$0")"
export SCULPTOR_FRONTEND_PORT="$port"
export SCULPTOR_PROXY_BASE="/proxy/$port/"

echo "Live preview -> https://<this-app-host>/proxy/$port/   (Vite on 127.0.0.1:$port)"
exec pnpm run dev
