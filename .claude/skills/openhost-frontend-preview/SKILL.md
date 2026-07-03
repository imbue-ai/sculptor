---
name: openhost-frontend-preview
description: |
  Live, hot-reloading preview of the Sculptor WEB frontend from a phone or any
  browser, served through the OpenHost nginx /proxy front. ONLY relevant when
  running INSIDE the openhost-deployed Sculptor (the container fronted by nginx on
  :5050, reachable at https://sculptor.<zone>/) — NOT for local or Electron dev.
  Frontend-only: it reuses the single shared backend, so it previews UI/frontend
  changes, not a per-workspace backend. Invoke when iterating on the web UI and
  wanting to see it live in a browser through the OpenHost SSO front.
user-invocable: true
---

# OpenHost frontend live preview (`/proxy/<port>/`)

Run a Vite dev server (HMR) for the Sculptor web UI and reach it from any
logged-in browser — including a phone — through the OpenHost nginx front, entirely
behind OpenHost's owner SSO. Nothing is exposed publicly.

## When this applies — OpenHost only

Use this ONLY inside the openhost-deployed Sculptor. Quick checks:
- `test -f /app/openhost-nginx.conf` (the nginx front config), and
- PID 1 is nginx: `ps -p 1 -o args=` -> `nginx ...` (backend is on loopback :5051).

If those are NOT true (local dev, Electron, a plain backend on :5050), this skill
does not apply — use normal `pnpm run dev` / `just frontend` there instead.

## How it works (read first)

- nginx owns :5050 (the only port OpenHost proxies) and routes `/proxy/<port>/*`
  -> `127.0.0.1:<port>`; everything else -> the backend on :5051.
- A preview is just a **Vite dev server** on a loopback port in the **51000-59999**
  band, served with `base=/proxy/<port>/`, dialing HMR back over
  `wss://...:443/proxy/<port>/`. Its `/api` + `/ws` calls are same-origin absolute,
  so they hit the ONE shared backend — there is no per-preview backend.
- So this previews **frontend** changes. Full-stack per-workspace instances (each
  with its own backend) are not supported on one origin: every backend would set
  the same session cookie on the same origin, and they collide.

## What surrounds a preview (already wired — don't rebuild it)

- **Switchboard + down-page:** `/proxy/` (no port) serves a self-contained page
  (`openhost-preview-fallback.html`, repo root) that scans the band from the
  browser and links to live previews. nginx serves the SAME page when a
  `/proxy/<port>/` target is dead, with a way back and an auto-reload poll that
  returns to the preview once its server is back.
- **Identity meta:** each preview's index.html carries
  `<meta name="sculptor-preview" content="<branch>@<sha>[*]">` (`*` = dirty
  tree), injected per request by `vite.base.config.ts` under
  `SCULPTOR_OPENHOST_PROXY`; a tree with no `.git` (e.g. `/app`) reports its
  serving path instead. The switchboard and the switcher plugin show this label.
- **Preview-switcher pill:** the `openhost-preview-switcher` plugin
  (`sculptor/frontend/plugins/`, auto-installed at boot by `openhost-run.sh`)
  renders a bottom-left pill in the deployed app listing live previews in
  51000-51099, and an amber badge with a way back when ON a preview. Switching
  preserves the `#/` route.
- **HMR keepalive:** the dev server pings every HMR client every 25s (also
  `SCULPTOR_OPENHOST_PROXY`-gated). Without it the idle HMR websocket gets
  killed by the edge and Vite hard-reloads the page about once a minute (and on
  every return from the background). If "random reloads" ever reappear, check
  the keepalive before suspecting app code.

## Run a preview

Pick a free port in 51000-59999, preferring the 51000-51099 range: the
`/proxy/` switchboard page (openhost-preview-fallback.html) quick-scans that
range on load, so previews there are found without a full-band scan. Launch it
**DETACHED** — do NOT use a tracked background task; this Sculptor will not
release your turn to the user while one is alive:

    cd <frontend-dir>
    setsid bash launch-preview.sh 51042 >/tmp/vite-51042.log 2>&1 </dev/null &

`<frontend-dir>` is either:
- **`/app/sculptor/frontend`** — preview the deployed UI as-is (its `node_modules`
  and `.venv` are already there, so it starts fast), or
- **your workspace's `sculptor/frontend`** — preview YOUR edits with HMR. A fresh
  worktree has no `node_modules`, so run `pnpm install` there once first (slow),
  then launch.

`launch-preview.sh <port>` sets `SCULPTOR_FRONTEND_PORT` + `SCULPTOR_OPENHOST_PROXY`
and runs `pnpm run dev -- --base=/proxy/<port>/` (base is a native Vite flag; the
env var only drives the OpenHost wss/HMR override). First start pre-bundles deps
(~tens of seconds) — watch
`/tmp/vite-<port>.log` for `ready in`. Then open, on any logged-in browser:

    https://sculptor.<your-zone>/proxy/51042/

Edits to the frontend source hot-reload live.

## Stop a preview

Do NOT `pkill -f vite...` — the pattern matches your own shell command and kills
the call. Stop by port -> pid -> process group:

    PID=$(ss -tlnpH | grep ':51042' | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2)
    PGID=$(ps -o pgid= -p "$PID" | tr -d ' ')
    kill -9 -"$PGID"

## Gotchas

- **Detached, not background.** Launch via `setsid ... &` from a normal foreground
  command so your turn releases. A `run_in_background` task or persistent `Monitor`
  blocks the user from talking to you until it ends.
- **One browser per workspace page.** Sculptor syncs tab state via `localStorage`,
  so the same workspace open in two browsers can desync — preview on a different
  page/tab than the one you're chatting in.
- **Same-origin trust.** Previews share the app's origin, so preview JS runs with
  your session's privileges — only run frontend code you trust.
