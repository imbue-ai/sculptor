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
#   - base is passed natively (`vite --base=/proxy/<port>/`) so Vite serves its
#     assets + HMR under that sub-path; SCULPTOR_OPENHOST_PROXY tells the Vite
#     config to dial HMR back over the TLS edge (wss, :443) — see vite.base.config.ts.
#   - The app's /api + /ws calls are same-origin ABSOLUTE (the web build compiles
#     API base to ""), so they bypass this Vite and hit the SHARED backend via
#     nginx. No per-preview backend is needed; full-stack previews aren't supported
#     on one origin (the session cookie would collide).
set -euo pipefail

port="${1:-}"
case "$port" in
  5[1-9][0-9][0-9][0-9]) ;;   # 51000-59999, the nginx preview band
  *) echo "usage: $(basename "$0") <port in 51000-59999>" >&2; exit 1 ;;
esac

cd "$(dirname "$0")"
export SCULPTOR_FRONTEND_PORT="$port"
export SCULPTOR_OPENHOST_PROXY=1

echo "Live preview -> https://<this-app-host>/proxy/$port/   (Vite on 127.0.0.1:$port)"
# `base` is a native Vite flag; the env var above only drives the wss/HMR override.
exec pnpm run dev -- --base="/proxy/$port/"
