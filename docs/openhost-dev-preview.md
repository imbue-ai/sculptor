# OpenHost mobile dev preview (`/proxy/<port>/`)

This branch (`maciek/oh-proxy-sidecar`) deploys Sculptor as a separate OpenHost
app (**`sculptor-dev`**) whose container front door is **nginx** instead of the
backend directly. nginx adds a reverse-proxy route so you can iterate on the web
UI **live from a phone**, with no SSH/tunnel and nothing made public.

## Topology

```
phone ─HTTPS (OpenHost owner SSO)─▶ OpenHost Caddy/router ─▶ container :5050 = nginx
                                                                  ├─ /proxy/<port>/*  → 127.0.0.1:<port>  (Vite dev server)
                                                                  ├─ /api/*, /ws/*    → 127.0.0.1:5051     (the ONE backend)
                                                                  └─ /                → 127.0.0.1:5051     (prod static UI)
```

- nginx owns 5050 (what OpenHost proxies); the backend moves to loopback **:5051**.
- A preview is just a **Vite dev server** sharing the **one** backend — not a
  second backend. Its `/api` + `/ws` are same-origin absolute, so they hit the
  backend through nginx, not through Vite.

## Running a preview

From the deployed `sculptor-dev` instance (or any workspace with the frontend deps):

```bash
sculptor/frontend/launch-preview.sh 51731     # any port in 51000-59999
# → open https://sculptor-dev.<zone>/proxy/51731/ on your phone
```

`launch-preview.sh` sets `SCULPTOR_FRONTEND_PORT` + `SCULPTOR_PROXY_BASE` and runs
`pnpm run dev`. The env var makes Vite (`vite.base.config.ts`) serve under
`base=/proxy/<port>/` and dial HMR back over `wss://…:443/proxy/<port>/`.

## Why the app must be "base-aware" (and can't be fully transparent)

We pass the URI through **unstripped** and require the dev server to know its
mount base (`base=/proxy/<port>/`). Making the proxied app *unaware* it's proxied
would mean nginx rewriting every absolute URL it emits — `/assets/…`, dynamic
imports, `import.meta.url`, `fetch("/api")`, the HMR WebSocket URL. `sub_filter`
can patch HTML text but not bundled/computed JS or WS URLs, so true transparency
is brittle/infeasible. Base-awareness is one Vite flag and robust, so that's the
contract.

What makes this cheap on the Sculptor side: the router is a **hash** router
(routes live in `#…`, immune to the sub-path) and the web API base compiles to
`""` (same-origin), so **no app code changes** are needed — only the Vite
dev-server config above.

## Iterating in-instance (after migrating onto `sculptor-dev`)

Once deployed, nginx is the container's front process and `/app` is the source:

- **nginx config** lives at `/app/openhost-nginx.conf`. Edit it, then reload with
  **no rebuild**: `nginx -s reload -c /app/openhost-nginx.conf`.
- **Sculptor backend**: edit under `/app`, then restart the backend process
  (it's the child launched by `/app/openhost-run.sh`).
- `/app` ships with its `.git` stripped; graft history back (as on prod) if you
  want to track local edits.

## Validate on first deploy (the finicky bits)

- HMR over a TLS sub-path is version-sensitive. If live-reload doesn't connect,
  the tuning knob is `server.hmr` in `vite.base.config.ts` (try setting
  `path: "/proxy/<port>/"`); a full-page reload still works meanwhile.
- Confirm the data WebSocket (`/ws`) connects (it should resolve to the origin
  root, not under the base).

## Security recap

Everything is already behind OpenHost owner SSO. `/proxy` adds defense-in-depth:
loopback-only upstreams (the OH router on `host.containers.internal` is
unreachable), port band 51000-59999 (can't target the backend itself), and the
Sculptor session cookie is stripped before reaching a preview. Backend-bearing
(full-stack) previews are deferred on the same-origin cookie-collision question —
see the cookie-scoping note in the workspace repo.
