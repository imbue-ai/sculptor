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
#   - SCULPTOR_OPENHOST_PROXY tells the Vite config to serve under base=/proxy/<port>/
#     (derived from SCULPTOR_FRONTEND_PORT) AND to dial its HMR client back over the
#     TLS edge (wss, :443) — see vite.base.config.ts.
#   - The app's /api + /ws calls are same-origin ABSOLUTE (the web build compiles
#     API base to ""), so they bypass this Vite and hit the SHARED backend via
#     nginx. No per-preview backend is needed; full-stack previews aren't supported
#     on one origin (the session cookie would collide).
set -euo pipefail

port="${1:-}"
case "$port" in
  5[1-9][0-9][0-9][0-9]) ;;   # 51000-59999, the nginx preview band
  *)
    echo "usage: $(basename "$0") <port in 51000-59999>" >&2
    echo "  prefer 51000-51099: the /proxy/ switchboard quick-scans that range" >&2
    exit 1
    ;;
esac

cd "$(dirname "$0")"
export SCULPTOR_FRONTEND_PORT="$port"
export SCULPTOR_OPENHOST_PROXY=1

echo "Live preview -> https://<this-app-host>/proxy/$port/   (Vite on 127.0.0.1:$port)"
# SCULPTOR_OPENHOST_PROXY (above) drives BOTH base=/proxy/<port>/ and the wss/HMR
# override in vite.base.config.ts (both derived from SCULPTOR_FRONTEND_PORT), so no CLI
# `--base` is needed. Do NOT add `pnpm run dev -- --base=…`: pnpm forwards a stray `--`
# that Vite reads as an end-of-options marker and silently drops the flag.
exec pnpm run dev
