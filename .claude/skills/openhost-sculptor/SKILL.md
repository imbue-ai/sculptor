---
name: openhost-sculptor
description: |
  Deploy, verify, and reset the self-hosted Sculptor app running as an OpenHost
  app (built from source via openhost.Dockerfile). Covers fresh deploys, updating
  or switching the deployed branch while keeping data, health-checking the live
  instance, and a full CLI-only reset to a fresh-onboarding instance. Wraps the
  `oh` CLI; the app name and repo are hardcoded in the scripts and the only
  per-machine value (your instance host) lives in .sculptor/.env. The common
  flows are one-command scripts in this skill's scripts/ folder.
user-invocable: true
---

# OpenHost Sculptor: deploy / verify / reset

Operate the self-hosted Sculptor app on an OpenHost compute space. Sculptor is
deployed there as an OpenHost app built **from source** (not a released binary):
OpenHost clones the repo at a branch, builds `openhost.Dockerfile`, runs the
container under rootless podman, and reverse-proxies HTTPS to it behind
OpenHost's owner login.

Everything here drives the **`oh` CLI** (OpenHost's app-management CLI) — no SSH
into the host for any normal flow. The four common flows are wrapped in scripts
under `scripts/`; the raw `oh` commands they run are shown alongside so you know
what each does.

## Config

This skill is Sculptor-specific, so the values are baked into the scripts — no
config file to set up:

- `APP` — `sculptor`, hardcoded in each script.
- `REPO` — `https://github.com/imbue-ai/sculptor`, hardcoded in each script.
- `BRANCH` — the repo's current git branch (`git rev-parse --abbrev-ref HEAD`).
- `HOST` — the public URL host that `verify.sh` curls (e.g. `sculptor.<your-zone>`).
  This is the **only per-machine value** — it embeds a personal subdomain, so it
  isn't committed. It lives in `.sculptor/.env` (gitignored via `**/.env`) as
  `OPENHOST_HOST`. `verify.sh` takes it as an argument; getting it from
  `.sculptor/.env` is the caller's job (see Verify below) — the script does no
  file I/O or prompting.

When you need `HOST` and `.sculptor/.env` doesn't have it yet, ask the user for
their instance host and save it so future runs don't have to ask:

```bash
echo "OPENHOST_HOST=sculptor.<your-zone>" >>.sculptor/.env   # gitignored
```

To run ad-hoc `oh` commands in a shell, just use those values directly, e.g.:

```bash
oh app status sculptor
oh app deploy "https://github.com/imbue-ai/sculptor@$(git rev-parse --abbrev-ref HEAD)" \
  --name sculptor --grant-permissions-v2 --wait
```

## Prereqs

- **`oh` CLI** installed and authenticated on this machine. Sanity check:
  `oh app list` should show your apps without an auth error. (Authenticate once
  with `oh instance login`.)
- **The branch must be pushed to GitHub first.** The deploy builds from
  `$REPO@$BRANCH` — OpenHost clones from GitHub, so unpushed local commits are
  invisible to it. Push (with the user's permission) before deploying.
- Repo root carries the deploy artifacts: `openhost.toml` (the app manifest —
  name, port `5050`, health check, persistent `app_data`) and `openhost.Dockerfile`
  (the from-source build recipe). The build context is always the repo root.

## How it runs

Knowing how the container is wired explains the deploy and reset behavior below.

- The Dockerfile `CMD` runs `python -m sculptor.cli.main --no-open-browser /workspace`
  from the built uv venv at **`/app/.venv`** — the backend serves the bundled web
  UI itself. **No Electron, no `just start`.** It's effectively `just backend` with
  static serving on and `/workspace` (a minimal pre-initialized git repo) as the
  initial project.
- The backend listens on `0.0.0.0:5050` inside the container; OpenHost proxies
  HTTPS at `https://$HOST/` behind its SSO owner login.
- Persistent state lives under **`/data/app_data/sculptor`** (env `SCULPTOR_FOLDER`)
  — DB, workspaces, downloaded agent binaries, and config. This dir is an OpenHost
  backed-up `app_data` mount, so it survives rebuilds and `oh app remove --keep-data`.
  Claude Code OAuth creds persist there too (`CLAUDE_CONFIG_DIR=/data/app_data/sculptor/claude`).

## Deploy / update

Each script deploys the current git branch (`BRANCH`) and runs `oh` with `--wait`
(the from-source build takes **~10 min** — uv sync, frontend `npm install` /
`generate-api` / `build`; don't assume it's instant).

### Fresh deploy — app name not yet in use

```bash
.claude/skills/openhost-sculptor/scripts/deploy.sh
# → oh app deploy "$REPO@$BRANCH" --name "$APP" --grant-permissions-v2 --wait
```

### Update, or switch branches — keep data

`oh app deploy` **refuses an existing app name** ("App name already in use"), so
redeploys remove first. `redeploy.sh` removes with `--keep-data` (persistent
`app_data` survives), then deploys the same or a different `$BRANCH`. `oh app
remove` blocks until the app is gone, so the deploy reuses the name cleanly.

```bash
.claude/skills/openhost-sculptor/scripts/redeploy.sh
# → oh app remove "$APP" --keep-data
# → oh app deploy "$REPO@$BRANCH" --name "$APP" --grant-permissions-v2 --wait
```

Note: `oh app reload "$APP" --update` only `git pull`s and rebuilds the *same*
branch already deployed — it does **not** switch branches. Switching branches
always means remove + deploy (i.e. `redeploy.sh`).

## Verify

After a deploy, confirm all three with one script. It takes your instance host as
an argument — load it from `.sculptor/.env` (see Config; add it there first if
missing):

```bash
. .sculptor/.env   # sets OPENHOST_HOST
.claude/skills/openhost-sculptor/scripts/verify.sh "$OPENHOST_HOST"
```

It checks:

1. **Right code is live** — `oh app status "$APP"` prints `git: <branch> @ <sha>`.
   Confirm the branch and SHA match what you deployed.
2. **It's serving** — `curl` the live URL.
   - **`302` = healthy.** That's the OpenHost SSO login redirect, not an error.
   - `502` / `503` = down (still building, crashed, or failed to bind).
3. **Clean boot** — `oh app logs "$APP"` shows `Uvicorn running on http://0.0.0.0:5050`
   and `Application startup complete`.

(OpenHost's own readiness probe hits the unauthenticated `/api/v1/health`, per
`openhost.toml`.)

## Reset — fresh-onboarding instance (CLI only, no SSH)

To wipe everything (DB, workspaces, Claude auth, completed-onboarding state) and
come back up at first-run onboarding, `reset.sh` removes the app **without**
`--keep-data` — which deletes the persistent `app_data` — then redeploys fresh.
It prompts for confirmation first, then rebuilds (~10 min).

```bash
.claude/skills/openhost-sculptor/scripts/reset.sh
# → oh app remove "$APP"            # no --keep-data: deletes persistent app_data
# → oh app deploy "$REPO@$BRANCH" --name "$APP" --grant-permissions-v2 --wait
```

`oh app remove --keep-data` (what `redeploy.sh` uses) preserves `app_data`,
**including a completed-onboarding config** — so a redeploy drops you straight
into the app. Use `reset.sh` when you specifically want fresh onboarding.

## Escape hatch

A few things the `oh` CLI can't do — exec a command inside the running container,
wipe only *part* of the data, or restart without a rebuild — require host access:
`oh instance ssh` opens a shell on the instance, from which you can drive
`podman` directly against the `openhost-$APP` container. You shouldn't need this
for any flow above; reach for it only for one-off inspection or surgical fixes.

## Gotchas

- **A returning browser can skip onboarding/Add Workspace.** Post-onboarding
  landing is driven by the browser's `sculptor-tabs` localStorage, not the server:
  the root route reopens the last active tab, and only with *no* saved tabs falls
  back to `/ws/new`. After a reset, a browser with stale tabs can land on home or a
  now-deleted workspace. Fix in the browser: `localStorage.clear()` in devtools,
  delete the `sculptor-tabs` key, or use an incognito window.
