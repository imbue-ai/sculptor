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
  tree), injected per request by `previewIdentity` in
  `sculptor/frontend/vite.base.config.ts` under `SCULPTOR_OPENHOST_PROXY`. A
  tree with no `.git` reports the frontend dir it serves from instead — e.g.
  `/app/sculptor/frontend` for a preview of the deploy image, which ships no
  git history. The switchboard and the switcher plugin show this label.
- **Preview-switcher pill:** the `openhost-preview-switcher` plugin
  (`sculptor/frontend/plugins/`, auto-installed at boot by `openhost-run.sh`)
  renders a bottom-left pill in the deployed app listing live previews in
  51000-51099, and an amber badge with a way back when ON a preview. Switching
  preserves the `#/` route.
- **HMR keepalive:** the dev server sends a no-op custom HMR event to every
  client every 25s (`previewHmrKeepalive` in
  `sculptor/frontend/vite.base.config.ts`, also `SCULPTOR_OPENHOST_PROXY`-gated).
  Without it the idle HMR websocket gets killed by the edge and Vite
  hard-reloads the page about once a minute (and on every return from the
  background). If "random reloads" ever reappear, check the keepalive before
  suspecting app code.

## Run a preview

Use a port in the 51000-51099 band. The preview-switcher pill in the
deployed app only auto-discovers that range (and the `/proxy/` switchboard page,
openhost-preview-fallback.html, quick-scans it on load), so a preview there shows
up without a full-band scan. A higher port (51100-59999) still works, but it will
**not** appear in the pill — you'd reach it only via the switchboard's full-band
scan or a direct `/proxy/<port>/` URL, so don't reach for a random high port. The
zero-friction way to get a valid one is to let the script pick: run
`launch-preview.sh` with **no argument** and it auto-selects a free 51000-51099
port (printed to the log).

Launch it **DETACHED** — do NOT use a tracked background task; this Sculptor will
not release your turn to the user while one is alive:

    cd <frontend-dir>
    setsid bash launch-preview.sh 51042 >/tmp/vite-51042.log 2>&1 </dev/null &

(or `setsid bash launch-preview.sh >/tmp/vite-preview.log 2>&1 </dev/null &` with
no port to auto-pick a free 510xx one — then read the chosen port and the
`ready in` line from the log.)

`<frontend-dir>` is either:
- **`/app/sculptor/frontend`** — preview the deployed UI as-is (its `node_modules`
  and `.venv` are already there, so it starts fast), or
- **your workspace's `sculptor/frontend`** — preview YOUR edits with HMR. A fresh
  worktree has no `node_modules`, so run `pnpm install` there once first (slow),
  then launch.

`launch-preview.sh [port]` sets `SCULPTOR_FRONTEND_PORT` + `SCULPTOR_OPENHOST_PROXY`
and runs `pnpm run dev` — the `/proxy/<port>/` base AND the OpenHost wss/HMR
override are both derived from those env vars in `vite.base.config.ts`, so do NOT
pass `--base` yourself (pnpm forwards a stray `--` that Vite reads as
end-of-options and silently drops the flag). First start pre-bundles deps
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
