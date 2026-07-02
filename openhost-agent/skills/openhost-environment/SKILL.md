---
name: openhost-environment
description: |
  How this OpenHost-hosted Sculptor environment works — storage and what survives
  restarts, where/how to add repositories and authorize gh, and the /proxy/<port>/
  capability for previewing loopback web apps from a browser. ONLY relevant when
  running inside an OpenHost deployment (detect via the OPENHOST_* env vars, e.g.
  OPENHOST_APP_NAME). Ships with the deploy image and is refreshed every release.
---

# Running inside an OpenHost-hosted Sculptor

You're in a Sculptor instance deployed as an **OpenHost** app if the `OPENHOST_*`
env vars are set (`OPENHOST_APP_NAME`, `OPENHOST_APP_DATA_DIR`,
`OPENHOST_ZONE_DOMAIN`, …). The public URL is
`https://$OPENHOST_APP_NAME.$OPENHOST_ZONE_DOMAIN/`, behind OpenHost's owner SSO.
If those vars are absent, this skill does not apply.

## Storage — what survives a restart/rebuild

- **Only `$OPENHOST_APP_DATA_DIR` (`/data/app_data/<app>`) persists** across
  reloads/rebuilds — it's the backed-up app-data mount. The DB, workspaces, Claude
  config/creds, and the gh token all live under it.
- **`/home` is wiped on every rebuild** — clones, `~/.gitconfig` (git identity +
  the `gh auth setup-git` credential wiring), and scratch are all lost.
- So keep anything durable under the app-data dir, **never in `/home`**.

## Adding repositories + gh auth

- **Add repos** via the app (Settings → Repositories) or `sculpt`
  (`sculpt workspace list --repo <path>` registers one). Clone to a **persisted**
  path, not `/home`.
- **gh auth:** `gh auth login` (device flow — paste the one-time code in a
  browser). The **token persists** (the gh config dir is under the app-data mount),
  but the git credential-helper wiring + identity live in `~/.gitconfig` and reset
  on rebuild. The deploy's run script re-runs `gh auth setup-git` and sets a
  gh-derived identity on boot (best-effort); if a push ever fails to auth after a
  rebuild, re-run `gh auth setup-git` and set `git config --global user.{name,email}`.

## `/proxy/<port>/` — preview a loopback web app from any browser

OpenHost publicly proxies **only port 5050** (behind owner SSO); an in-container
nginx fronts it and adds a reverse proxy:

- **`https://$OPENHOST_APP_NAME.$OPENHOST_ZONE_DOMAIN/proxy/<port>/`** forwards to
  `127.0.0.1:<port>` for any port in **51000–59999**, all behind SSO. Nothing is
  made public.
- Use it to preview **any** simple loopback web app or dev server (not just Vite),
  including from a phone. The URI is passed through **unstripped**, so the app must
  be **base-aware** — served under `/proxy/<port>/` (e.g. a dev server's base/prefix
  option), since fully transparent rewriting of an app's absolute URLs isn't done.
- **Caveat — shared origin:** the preview shares the root app's origin, so its
  cookies/paths must **not collide** with Sculptor's (the session cookie in
  particular). Simple apps with their own non-overlapping cookies/paths are fine; a
  second full Sculptor backend is not (its session cookie would collide).
- For the **Sculptor web frontend** specifically, use the `openhost-frontend-preview`
  skill / `sculptor/frontend/launch-preview.sh` (when working in the sculptor repo).

## Turn-handling (matters here)

This Sculptor does **not** release your turn to the user while a tracked
`run_in_background` Bash task or a persistent `Monitor` is alive. Launch long-lived
servers **detached** from a normal foreground command instead:
`setsid <cmd> >/tmp/x.log 2>&1 </dev/null &`. Detached/orphaned processes keep
running and don't hold the turn; check on them later via `ps` / `curl` / log reads.

---
*This skill ships with the OpenHost deploy image and is refreshed on every release,
so it stays current. The owner's standing instructions live in the seeded
`AGENTS.md` in the same config dir.*
