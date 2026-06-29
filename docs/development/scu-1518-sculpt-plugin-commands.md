# Design: `sculpt` commands for frontend plugins (SCU-1518)

Status: **draft v2** — decisions taken in the 2026-06-23 review are folded in;
ready for a thorough read.

## Goal

Let an agent (or a developer) that is iterating on a frontend plugin **load it
into the live Sculptor instance, reload it after edits, and inspect what it did**
— all from the `sculpt` CLI, without manual clicking in Settings → Plugins.

From the ticket:

> Being able to one-off load a plugin file that agent is working on, or reloading
> it with a command. Also inspecting the state of a plugin (its persisted
> configuration, what did it register) and its status (did it load, did it fail).
> Primary use case is enabling agents to develop plugins locally and load them
> into the live Sculptor instance.

This builds directly on the frontend-plugin system shipped in **SCU-1517**.

## Correction to the SCU-1517 deferral note

The comment on this ticket (deferred from SCU-1517) describes a design that **was
not the one that shipped**. It talks about serving plugins from
`/plugins/from-workspace/<workspace_id>/…`, an `allow_plugins_from_workspaces`
config flag, and a per-workspace consent/DB model. **None of that exists in
`main`.**

What SCU-1517 *actually* shipped is a **drop-in directory** model:

- Plugins live in `~/.sculptor/plugins/<id>/` (the backend data folder's
  `plugins/` subdir).
- `GET /api/v1/plugins/local` enumerates subdirs containing a `manifest.json`
  (`web/app.py:1538`).
- `GET /api/v1/plugins/dir` reports the directory for display (`web/app.py:1581`).
- A `StaticFiles` mount at `/plugins/local` serves the bytes, inserted ahead of
  the SPA catch-all (`web/middleware.py:51`, `mount_plugin_files`). **Not gated**
  by any flag; CORS is the only boundary.
- The frontend discovers these at boot and via a manual **Refresh** button.

So the SCU-1518 mechanism plugs into the data-dir + `/plugins/local` mount, **not**
a workspace-served route.

> Terminology trap: `sculptor/sculptor/common/plugin.py` is the **Claude-Code
> agent-plugin** system (skills like `/help`), a *different* subsystem that also
> uses the word "plugin" and a `plugins/` dir. This ticket is about the
> **frontend/UI** plugin system in `sculptor/frontend/src/plugins/`.

## Decisions (2026-06-23 review)

These resolve the v1 open questions; the rest of the doc reflects them.

1. **Two flags, not one.** Keep `enable_frontend_plugins` as the front-end-feature
   gate (slated to default *on* soon). Add a **sibling switch** that gates
   *agent-driven* load/reload via `sculpt`. The two are independent: the feature
   can be on for everyone while agent-driven loading stays opt-in.
2. **No per-workspace consent, no consent DB.** Agents are not sandboxed — they can
   already write directly into `~/.sculptor/plugins/`. A per-workspace allowance
   would add ceremony without adding real security. The **agent-loading switch is
   the entire consent surface**: turning it on means "agents may install and run
   frontend code in my Sculptor UI." That is the honest, one-time decision.
3. **`load` separates target from persistence — no magic.** The *target* (local
   path vs URL) is auto-detected, but whether an install is **ephemeral (dev)** or
   **permanent** is an **explicit flag** (`--persist`, default off = dev), not
   inferred from URL-ness. The L1-vs-L2 question dissolves into "what does load
   *do*" — see "What `sculpt plugin load` does".
4. **Dev installs are nested in a reserved, clearly-temporary location** —
   `~/.sculptor/plugins/dev/<workspace-id>/<plugin-id>/` — so they're visibly not
   permanent drop-ins and two workspaces can't collide on the same id. Permanent
   installs land in the top-level `~/.sculptor/plugins/<plugin-id>/` (a normal
   drop-in) or as a URL source.
5. **The bridge is a scatter-gather request/response** (correlation ids), not
   fire-and-forget — `load` must report success/failure from the renderer, and
   `inspect` reuses the same return channel.
6. **Multi-renderer is handled from day one** (not deferred). Results are always
   keyed by a **per-connection renderer id**, and the CLI applies a strict,
   documented preference to pick one (or `--all` to see every window). Two open
   windows must never crash or behave unexpectedly — Electron-first only means we
   *optimize* for the common one-window case.
7. **Electron-first, workspace-scoped.** Browser-direct isn't a v1 target — the
   design stays backend-mediated (no renderer-side filesystem IPC), so it doesn't
   *break* browser mode, we just don't promise it. `sculpt plugin …` runs inside a
   workspace and infers the workspace id (as `sculpt signal` infers the agent id).
8. **Inspect must not leak secrets.** Per-plugin settings (`usePluginSetting`,
   localStorage `sculptor-plugin:<id>:<key>`) can hold credentials — the Linear
   example plugin stores its API key there today. `inspect` reports **which config
   keys are set, never their values**.

## Current architecture (what we build on)

### How the renderer and backend talk

- **One real-time push channel:** a WebSocket at `/api/v1/stream/ws`
  (`web/app.py:3284`, `stream_everything` in `web/streams.py:453`) carrying a
  single `StreamingUpdate` envelope of camelCased deltas, fanned into Jotai atoms
  by `useUnifiedStream()` (`frontend/src/common/state/hooks/useUnifiedStream.ts`).
  No SSE, no polling.
- **The proven "drive the renderer from the backend" pattern is UI Actions**
  (`web/ui_actions.py`): a REST `POST` calls `publish_ui_action(action)`, fanned
  over the stream to every connected renderer, reacted to in `useUnifiedStream`.
  Existing action types: `OpenFileUiAction`, `WebviewCommandUiAction`, published
  by `POST /api/v1/workspaces/{id}/ui/open-file`, `…/ui/webview/refresh`
  (`web/app.py:1200`, `:1299`). **This is the template for the command channel.**
- **No per-renderer addressing.** Auth is a single shared session token; actions
  **broadcast** to every connected renderer, filtered only by the `workspace_id`
  in the payload and the optional `?scope=` on the WS. (Fine for Electron-first,
  where we expect one window.)

### Where plugin state actually lives — the constraint that shapes `inspect`

**All live plugin state is renderer-only:**

- Per-source status/error: `pluginSourceStatesAtom` (`pluginRegistry.ts:110`) — a
  union `loading | loaded | error{phase,message} | disabled | shadowed | missing`.
  Not persisted; rebuilt each boot.
- What a plugin registered: `pluginPanelsAtom`, `pluginSettingsComponentsAtom`,
  `pluginOverlaysAtom`. Panels carry `pluginId`; settings are keyed by id;
  overlays are not attributable from the atom alone (only the manager's private
  `disposersBySource` knows the full per-source picture).
- Persisted config (browser **localStorage**, no backend mirror):
  `sculptor-plugin-sources`, `…-disabled-sources`, `…-enabled-sources`, and
  per-setting `sculptor-plugin:<pluginId>:<key>`.

The backend can read **none** of this — not even in Electron. So `inspect` cannot
be served from existing backend state; it must ask the renderer (the bridge below).

### Load / reload mechanics already present

- A **source** is a string (URL or dir path resolving to a `manifest.json`); a
  **plugin** is `manifest.id`. Many sources → one id; one active per id, the rest
  `shadowed`.
- `reloadSource()` = `unloadSource()` then `loadSource(…, cacheBust=Date.now())`,
  which appends `?t=<ts>` so the browser re-fetches the ESM bundle and re-runs
  `activate()`, replacing registrations (`pluginManager.tsx:621`). **Reload already
  does what the dev loop needs** — we just trigger it remotely.
- `refreshLocalSources()` re-scans `/plugins/local` (`pluginManager.tsx:434`).

### Electron vs browser (Electron is the v1 target)

- `isElectron()` = presence of the preload-injected `window.sculptor`
  (`frontend/src/electron/utils.ts:7`).
- **Plugins are served over HTTP by the backend in both modes** — the renderer
  never reads plugin files from disk (`web/middleware.py:51`). So a
  backend-mediated design works in Electron and doesn't crash in browser even
  though browser isn't a v1 target. **Keep every filesystem op backend-side.**

## What `sculpt plugin load` does — the packaging operation

This is the piece worth designing first; the L1/L2 question falls out of it. There
are **two independent axes**, and `load` keeps them explicit rather than inferring
one from the other:

- **Target** (auto-detected): a **local path** (workspace files) or a **URL**.
- **Mode** (explicit `--persist` flag, default off): **dev** (ephemeral, for
  iteration) or **persistent** (the permanent end-state).

`sculpt plugin load <target> [--persist]` runs inside a workspace and infers the
workspace id.

### Dev mode (default) — the iteration loop

Place the plugin in a **reserved, clearly-temporary** location and load it:

1. **Resolve** the `manifest.json`; read `id`, `entry`, and any referenced assets.
2. **Package** (path target only) — gather the manifest + entry bundle + referenced
   assets into a self-contained set. `load` does **not** build: the agent builds
   first (or writes a no-build plugin) and `load` packages whatever the manifest
   points at.
3. **Place** (path target) **through a backend endpoint** (the CLI streams the
   packaged files) into the reserved dev tree:
   `~/.sculptor/plugins/dev/<workspace-id>/<plugin-id>/`. Going through the backend
   means it works whether or not the workspace shares the host filesystem (worktree
   vs container), the agent-loading switch gates it server-side in one code path,
   and nothing relies on the agent reaching the host home directly. For a URL
   target there's nothing to place.
4. **Register + trigger** load (or reload, if that id is already active) over the
   command channel, **tagged as dev** (see the dev indicator in `inspect`/`list`),
   and **return the result** — `loaded` or `error{phase,message}` — so the CLI
   exits non-zero on a failed activate.

Dev sources are **persisted across restart** (registered like any source) so the
plugin survives a reload of the window or the app; if the dev files have been
removed the source settles cleanly into `missing`/`error` rather than breaking the
boot. The agent is expected to clean up its dev source when done (see lifecycle).

**Why placement is L2, not L1:** a path target has to turn workspace files into
backend-served bytes; placing them under the existing `/plugins/local` static mount
reuses all SCU-1517 serving infrastructure and adds **no new executable-file
endpoint**. Live workspace-serving (L1) would add a serving surface for no real
gain now that placement is cheap and the switch is the gate.

### Persistent mode (`--persist`) — the permanent install

The end-state once the user is happy with the plugin:

- **Path target:** copy the packaged files into the **top-level**
  `~/.sculptor/plugins/<plugin-id>/` — a normal drop-in, **not** workspace-scoped,
  discovered like any user-placed plugin.
- **URL target:** register the URL as a **persistent url-source** (the same
  mechanism as a user-added source; persisted in `pluginSourcesAtom`).

Either way it survives restarts and is no longer tagged dev.

### Lifecycle: iterate → install → clean up

The intended flow, and why both modes plus a clean remove are needed:

1. Agent iterates: `sculpt plugin load ./my-plugin` (dev) + `reload` repeatedly.
2. User likes it: `sculpt plugin load ./my-plugin --persist` (copy to the top-level
   dir) **or** host it and `sculpt plugin load https://… --persist`.
3. Agent cleans up its dev version: `sculpt plugin remove <id>`, which unregisters
   the dev source and deletes its files under `dev/<workspace-id>/<id>/`.

Steps 2 and 3 briefly coexist as two sources for the same id; the existing
shadow-by-priority behaviour handles that until the dev source is removed.

### The reserved `dev/` subdir vs passive discovery

The `dev/` name under `~/.sculptor/plugins/` is **reserved** (add it to the
existing reserved-plugin-name check so a user can't create a top-level plugin
literally named `dev`). Passive discovery (`GET /api/v1/plugins/local`) scans one
level deep, so a `dev/` directory — which holds no `manifest.json` of its own —
is naturally skipped and never mistaken for a plugin. Dev plugins are loaded
**imperatively** (the command carries the exact nested manifest URL) and are
re-registered from their persisted source on the next boot.

## The bridge: command out + result back

Generalize UI Actions into a request/response with a correlation id. One mechanism
serves `load` / `reload` / `unload` **and** `inspect`:

1. CLI → `POST /api/v1/plugins/command` (workspace-scoped) with
   `{op, args, correlationId}`.
2. Backend `publish_ui_action(PluginCommandUiAction{op, args, correlationId})` over
   the WS.
3. Each connected renderer handles it in `useUnifiedStream`, runs the matching
   `pluginManager` method, then POSTs its outcome to
   `POST /api/v1/plugins/command/{correlationId}/result`, **tagged with its own
   renderer id**.
4. The backend correlates (a waiter keyed by `correlationId`, like a future),
   gathers every result that arrives within a short window, and returns them
   **keyed by renderer id** — or times out with a clear message: *"no Sculptor
   window responded — is it running with frontend plugins enabled?"*.

### Multi-renderer is designed in, not deferred

Commands broadcast to all of a user's renderers and there's no per-client
addressing today, so the API is **multi-result from the start** — it always
returns a list keyed by renderer id, never a single value that silently assumes one
window. This makes two windows a non-event rather than a crash. Concretely:

- **Renderer id** = a stable per-page-load id (sessionStorage), one per WebSocket
  connection (~one per window). Each result carries it, plus light metadata the CLI
  can rank on: whether that renderer's active workspace matches the command's
  workspace, and a last-active timestamp.
- **Strict preference** (CLI default, documented): pick the renderer whose active
  workspace matches the command's workspace; tie-break by most-recently-active;
  final tie-break by renderer id (deterministic). `--all` shows every renderer's
  result instead of the preferred one.
- **`load` / `reload`** apply to every renderer that has the plugin (so all windows
  reflect the dev plugin); the CLI reports the preferred renderer's result by
  default and a per-renderer breakdown under `--all` / `--json`. A failure in the
  preferred renderer is the CLI's non-zero exit.
- **`inspect`** reports the preferred renderer's snapshot and notes when other
  renderers exist (and may disagree).

Keeping the wire shape multi-result avoids a v2 breaking change; "Electron-first"
just means we tune defaults for the one-window case, not that two windows are
unhandled.

## Inspect: what we report (and what we must not)

`sculpt plugin inspect <id>` (and `list`) collect, via the bridge, a **curated,
redacted** snapshot the renderer assembles explicitly — it never dumps localStorage
wholesale:

- **status** — `loaded | error{phase,message} | shadowed{activeSource} | disabled |
  missing`.
- **origin** — `dev` (workspace-scoped, from `dev/<ws-id>/<id>/`) vs `installed`
  (top-level drop-in) vs `url` vs `builtin`. The **dev indicator** is surfaced
  everywhere a plugin is listed (CLI `list`/`inspect`, and a small badge in the
  Settings → Plugins row) so a work-in-progress dev plugin is never confused with a
  permanent install.
- **registrations** — panels (ids/titles), settings (present y/n), overlays (ids):
  names only.
- **persisted config** — the **key names** that are set for the plugin, and whether
  each is set; **never the values**. Per-plugin settings are opaque strings that may
  be credentials (the Linear plugin stores an API key via `usePluginSetting`
  today). No `--reveal` flag in v1.

## The agent-loading switch (the entire consent surface)

A new `UserConfig` flag (closed by default), **sibling to**
`enable_frontend_plugins`, gating `sculpt plugin load/reload`. Honest copy in
Settings → Plugins: *"Allow agents to install and run frontend plugins in your
Sculptor UI."*

- When **closed**, `sculpt plugin load/reload` **errors clearly** ("agent plugin
  loading is disabled; enable it in Settings → Plugins") rather than silently
  no-opping.
- No per-load prompt and no per-workspace allowance in v1 — the agent already has
  the access a prompt would gate, so the global switch is the meaningful decision.
  (We can still surface a non-blocking notification when a plugin is loaded, for
  transparency.)
- `enable_frontend_plugins` still independently gates whether the plugin runtime
  exists at all; if it's off, `inspect` returns "no plugin runtime," distinct from
  "no window connected."

Deferred (note only): real auth on the static plugin routes in remote/headless
mode. Out of scope for the dev loop.

## CLI surface (`sculpt plugin …`)

A new `plugin_app` Typer sub-app in `tools/sculpt/sculpt/main.py`, talking to the
backend via the generated client (`get_authenticated_client`), like `sculpt
signal`. Runs inside a workspace; infers the workspace id.

- `sculpt plugin load <path|url> [--persist]` — default (dev) packages + places a
  path into the workspace `dev/` tree (or registers a dev URL source) and loads it;
  `--persist` installs permanently (path → top-level drop-in, url → persistent
  url-source). Returns the (preferred-renderer) load result; non-zero on failure.
- `sculpt plugin reload [<id>|<path>]` — re-package (for path) + cache-bust reload.
- `sculpt plugin remove <id>` — unregister and **delete** a dev install's files
  (the cleanup step of the lifecycle). For non-dev sources, unregisters only.
- `sculpt plugin unload <id>` — unload from the running UI without deleting files.
- `sculpt plugin list` — all plugins (builtin / installed / url / **dev**) with live
  status and the dev indicator.
- `sculpt plugin inspect <id>` — status, origin, registrations, **redacted** config.
- `sculpt plugin dir` — print the data plugins dir (`/plugins/dir`).
- All: `--json` for agents; `--all` for per-renderer results; clear non-zero exits
  on "disabled / not connected / load failed".

## Phased implementation plan

1. **Bridge (multi-result from the start).** `PluginCommandUiAction` + `POST
   /api/v1/plugins/command` + correlation-id waiter + result endpoint that gathers
   per-renderer-id results; renderer handler in `useUnifiedStream` (carrying its
   renderer id) calling `pluginManager.load/reload/unload`. Generalizes the
   open-file/webview pattern.
2. **Agent-loading switch.** New `UserConfig` flag (closed default) + Settings
   toggle + server-side enforcement on the command endpoint.
3. **Dev placement (path form).** Reserve the `dev/` subdir name; endpoint that
   receives a packaged plugin and writes it to
   `~/.sculptor/plugins/dev/<ws-id>/<id>/`; the static mount serves the nested path;
   register a persisted dev source; command fires the load and returns the result.
4. **Persistent installs (`--persist`).** Path → copy to top-level
   `~/.sculptor/plugins/<id>/`; URL → persistent url-source. Plus `remove` to
   unregister + delete a dev install.
5. **Inspect + dev indicator.** Renderer assembles the redacted snapshot (status,
   origin, registrations, redacted config); a dev badge in the Settings row; CLI
   reads it via the bridge.
6. **CLI sub-app** wiring all of the above, with `--json` and `--all`.
7. **Tests.** Mirror `test_plugin_loader.py` (flip both flags via config populator,
   drive via the CLI/endpoint, assert on the settings POM `data-status` /
   `data-phase` hooks, and the dev indicator). Electron-marked variant where it
   matters; a two-renderer case for the strict-preference selection.

Later: browser support; host-side `sculpt`; `--build` / `--watch`; auth on the
static routes; a `promote` convenience that folds install + dev-cleanup into one.

## Remaining open questions

1. **Packaging boundary** — confirm v1 expects a pre-built `entry` and never runs a
   build (agent builds first); `--build` is a later add. *(Tentatively yes.)*
2. **Switch naming** — confirm the new sibling flag name (proposing
   `allow_agent_plugin_loading`).
3. **`remove` ergonomics** — is a separate `remove` enough, or do we want a single
   `promote` (install permanently + delete the dev source) as the one-shot "I'm
   done" command? (Listed as later work; flagging in case it should be v1.)
