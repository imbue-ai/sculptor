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

# The preview-switcher pill in the deployed app only auto-discovers previews in
# the 51000-51099 quick band (a browser can't scan the whole 9000-port band on
# every open — the /proxy/ switchboard's full-band scan covers the rest). So
# default to a free port in that band when none is given, and warn on an explicit
# port outside it: otherwise the preview is reachable only by a direct URL or the
# switchboard, never the pill. Keep this band in sync with QUICK_BAND_* in
# sculptor/frontend/plugins/openhost-preview-switcher/src/scan.ts.
quick_band_start=51000
quick_band_end=51099

pick_free_quick_port() {
  # Ports currently bound (listening), one per line, from a single ss snapshot.
  # grep matches nothing when there are no listeners at all; tolerate that
  # (|| true) rather than letting the empty match trip pipefail under set -e.
  local used
  used="$(ss -tlnH 2>/dev/null | grep -oE ':[0-9]+' | tr -d ':' | sort -u)" || true
  local p
  for ((p = quick_band_start; p <= quick_band_end; p++)); do
    grep -qx "$p" <<<"$used" || { echo "$p"; return 0; }
  done
  return 1
}

port="${1:-}"
if [[ -z "$port" ]]; then
  if ! port="$(pick_free_quick_port)"; then
    echo "no free port in $quick_band_start-$quick_band_end; pass an explicit port in 51000-59999" >&2
    exit 1
  fi
  echo "auto-selected free port $port (in the preview-switcher pill's $quick_band_start-$quick_band_end scan band)"
fi

case "$port" in
  5[1-9][0-9][0-9][0-9]) ;;   # 51000-59999, the nginx preview band
  *)
    echo "usage: $(basename "$0") [port in 51000-59999]   (default: a free port in $quick_band_start-$quick_band_end)" >&2
    echo "  the preview-switcher pill only auto-discovers $quick_band_start-$quick_band_end; higher ports need the /proxy/ switchboard or a direct URL" >&2
    exit 1
    ;;
esac

if (( port < quick_band_start || port > quick_band_end )); then
  echo "WARNING: port $port is outside $quick_band_start-$quick_band_end, so the preview-switcher pill will NOT list it." >&2
  echo "         Reach it via the /proxy/ switchboard (full-band scan) or the direct /proxy/$port/ URL — or use a $quick_band_start-$quick_band_end port to get the pill." >&2
fi

cd "$(dirname "$0")"
export SCULPTOR_FRONTEND_PORT="$port"
export SCULPTOR_OPENHOST_PROXY=1

echo "Live preview -> https://<this-app-host>/proxy/$port/   (Vite on 127.0.0.1:$port)"
# SCULPTOR_OPENHOST_PROXY (above) drives BOTH base=/proxy/<port>/ and the wss/HMR
# override in vite.base.config.ts (both derived from SCULPTOR_FRONTEND_PORT), so no CLI
# `--base` is needed. Do NOT add `pnpm run dev -- --base=…`: pnpm forwards a stray `--`
# that Vite reads as an end-of-options marker and silently drops the flag.
exec pnpm run dev
