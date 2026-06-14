---
name: openhost-sculptor
description: |
  Deploy, verify, and reset the self-hosted Sculptor app running as an OpenHost
  app (built from source via openhost.Dockerfile). Covers fresh deploys, updating
  or switching the deployed branch, health-checking the live instance, getting a
  shell inside the container, and the three reset levels (surgical re-onboard,
  clear gh auth, full wipe). Set the app name and host (the only
  instance-specific parts) at the top of a session and substitute throughout for
  your own OpenHost compute space.
user-invocable: true
---

# OpenHost Sculptor: deploy / verify / reset

Operate the self-hosted Sculptor app on an OpenHost compute space. Sculptor is
deployed there as an OpenHost app built **from source** (not a released binary):
OpenHost clones the repo at a branch, builds `openhost.Dockerfile`, runs the
container under rootless podman, and reverse-proxies HTTPS to it behind
OpenHost's owner login.

This skill is instance-generic. The instance-specific values (app name and your
personal host) live in a gitignored file, `openhost.env`, in this skill's folder
— source it at the top of any session and substitute throughout:

```bash
# Load your local instance config (gitignored; see openhost.env.example).
set -a; [ -f .claude/skills/openhost-sculptor/openhost.env ] && \
  . .claude/skills/openhost-sculptor/openhost.env; set +a
: "${BRANCH:=$(git rev-parse --abbrev-ref HEAD)}"   # default to the current branch
CONTAINER=openhost-$APP                             # podman container name (always openhost-<app>)
```

This sets `APP`, `HOST`, `REPO` (and optionally `BRANCH`). If `openhost.env`
doesn't exist yet, copy `openhost.env.example` to `openhost.env` and fill it in
(only `HOST` is personal); never commit `openhost.env`.

## Prereqs

- **`oh` CLI** installed and authenticated on this machine (the OpenHost CLI).
  Sanity check: `oh app list` should show your apps without an auth error.
- **The branch must be pushed to GitHub first.** The deploy builds from
  `$REPO@$BRANCH` — OpenHost clones from GitHub, so unpushed local commits are
  invisible to it. Push (with the user's permission) before deploying.
- Repo root carries the deploy artifacts: `openhost.toml` (the app manifest —
  name, port `5050`, health check, persistent `app_data`) and `openhost.Dockerfile`
  (the from-source build recipe). The build context is always the repo root.

## How it runs

Knowing how the container is wired explains every reset and gotcha below.

- The Dockerfile `CMD` runs `python -m sculptor.cli.main --no-open-browser /workspace`
  from the built uv venv at **`/app/.venv`** — the backend serves the bundled web
  UI itself. **No Electron, no `just start`.** It's effectively `just backend` with
  static serving on and `/workspace` (a minimal pre-initialized git repo) as the
  initial project.
- The backend listens on `0.0.0.0:5050` inside the container; OpenHost proxies
  HTTPS at `https://$HOST/` behind its SSO owner login.
- Persistent state lives under **`/data/app_data/sculptor`** (env `SCULPTOR_FOLDER`)
  — DB, workspaces, downloaded agent binaries, and config. This dir is an OpenHost
  backed-up `app_data` mount, so it survives rebuilds and `--keep-data` removes.
  - Claude Code OAuth creds: `CLAUDE_CONFIG_DIR=/data/app_data/sculptor/claude`
  - GitHub CLI token: `GH_CONFIG_DIR=/data/app_data/sculptor/gh`

## Deploy / update

### Fresh deploy (app name not yet in use)

```bash
oh app deploy "$REPO@$BRANCH" --name "$APP" --grant-permissions-v2 --wait
```

The from-source build takes **~10 min** (uv sync, frontend `npm install` /
`generate-api` / `build`, gh install). `--wait` blocks until it finishes — monitor
it; don't assume it's instant.

### Update an already-deployed app, or switch branches

`oh app deploy` **refuses an existing app name** ("App name already in use"). To
redeploy (same branch rebuilt, or a *different* branch), remove first while keeping
the data, then deploy:

```bash
oh app remove "$APP" --keep-data        # preserves /data/app_data/sculptor
oh app deploy "$REPO@$BRANCH" --name "$APP" --grant-permissions-v2 --wait
```

Notes:
- **There is no `oh app start`.** Lifecycle is deploy / remove / reload.
- **`oh app reload "$APP" --update` does NOT switch branches.** It only `git pull`s
  the *same* branch already deployed and rebuilds. Switching branches always means
  `remove --keep-data` + `deploy`.

## Verify

After a deploy, confirm all three:

1. **Right code is live** — `oh app status "$APP"` prints `git: <branch> @ <sha>`.
   Confirm the branch and SHA match what you deployed.
2. **It's serving** — hit the live URL:
   ```bash
   curl -s -o /dev/null -w "%{http_code}" "https://$HOST/"
   ```
   - **`302` = healthy.** That's the OpenHost SSO login redirect, not an error.
   - `502` / `503` = down (still building, crashed, or failed to bind).
3. **Clean boot** — `oh app logs "$APP"` should show:
   - `Uvicorn running on http://0.0.0.0:5050`
   - `Application startup complete`

   (OpenHost's own readiness probe hits the unauthenticated `/api/v1/health`, per
   `openhost.toml` — useful to know when reading why the router marks the app up.)

## Container access

For resets and inspection, go through the instance SSH, then drive podman. After
`oh instance ssh`, set this remote-shell boilerplate so `podman` is on `PATH` and
talks to the rootless socket:

```bash
export XDG_RUNTIME_DIR=/run/user/1000
export PATH=/home/host/openhost/.pixi/envs/default/bin:$PATH
```

Then:

- Run a command inside the container:
  ```bash
  podman exec "$CONTAINER" sh -c "<cmd>"      # CONTAINER = openhost-sculptor
  ```
- **Host path** of the persistent data dir (bind-mounted to `/data/app_data/sculptor`):
  ```
  /home/host/.openhost/local_compute_space/persistent_data/app_data/sculptor
  ```
- Auth file locations (inside the container):
  - Claude creds: `/data/app_data/sculptor/claude/.credentials.json`
  - gh token: `/data/app_data/sculptor/gh/hosts.yml`

## Resets

Three levels, fastest first. Levels 1 and 2 need **no rebuild**. All run from the
instance SSH with the boilerplate above.

### 1. Surgical re-onboarding — keep Claude + gh auth + DB

The onboarding gate is `internal/config.toml`: the app shows onboarding **iff** that
file is missing/invalid at startup. It's read **once at startup**, so the restart is
**required**.

```bash
podman exec "$CONTAINER" rm -f /data/app_data/sculptor/internal/config.toml
podman restart "$CONTAINER"
```

After restart, logs show `No config file found ... will require onboarding`.

### 2. Clear only gh auth — re-test the in-app gh device-flow sign-in

Keeps Claude auth, DB, and onboarding state; only wipes the GitHub CLI token.

```bash
podman exec "$CONTAINER" sh -c "find /data/app_data/sculptor/gh -mindepth 1 -delete"
podman restart "$CONTAINER"
```

### 3. Full wipe — fresh everything (loses Claude + gh auth, DB, workspaces)

Re-onboard from scratch. **Stop first** so nothing holds files open, then wipe the
**host** dir with `podman unshare`, then start:

```bash
podman stop "$CONTAINER"
podman unshare sh -c "find /home/host/.openhost/local_compute_space/persistent_data/app_data/sculptor -mindepth 1 -delete"
podman start "$CONTAINER"
```

Why `podman unshare` (not a plain host `rm`, not `podman exec rm`):
- The files are owned by the **container-mapped UID**, so a plain host `rm` fails on
  permissions; `podman unshare` enters that user namespace where they're owned by you.
- `podman exec rm` **while the app is running** fails on `internal/` because the live
  app keeps re-creating `database.db` — hence stop first.

Alternative full wipe: `oh app remove "$APP"` **without** `--keep-data` also clears
the data, but then you must redeploy and rebuild (~10 min). Prefer the
stop/wipe/start above for a fast full reset with no rebuild.

## Gotchas

- **`--keep-data` preserves a completed-onboarding `config.toml`.** So a redeploy
  with `--keep-data` skips onboarding and drops you straight into the app. To force
  fresh onboarding after a redeploy, do reset level 1 (surgical) afterward, or a
  full wipe (level 3).
- **Post-onboarding landing is driven by the browser's `sculptor-tabs` localStorage,
  not the server.** The root route reopens the last active tab; only with *no* saved
  tabs does it fall back to `/ws/new` (Add Workspace). A returning browser with stale
  tabs can land on home or a now-deleted workspace instead of onboarding/Add
  Workspace. Fix in the browser: `localStorage.clear()` in devtools, delete the
  `sculptor-tabs` key, or use an incognito window.
- **After a full wipe, any browser's `sculptor-tabs` points at deleted workspaces** →
  dead routes. Clear the site's localStorage (as above) before re-testing.
