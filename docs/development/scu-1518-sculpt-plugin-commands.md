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
3. **`sculpt plugin load` is polymorphic** on its argument: a **path** is a
   dev-loop install (package the workspace files and place them where the backend
   serves them), a **URL** is a permanent install (a persistent url-source). The
   L1-vs-L2 question dissolves into "what does load *do*" — see the next section.
4. **Local (path) installs nest by workspace id** so two workspaces iterating on
   the same plugin id don't collide.
5. **The bridge is a scatter-gather request/response** (correlation ids), not
   fire-and-forget — because `load` itself must report success/failure back from
   the renderer, and `inspect` reuses the same return channel.
6. **Electron-first.** Browser-direct is not a v1 target. The design stays
   backend-mediated (no renderer-side filesystem IPC), so it doesn't *break*
   browser mode; we just don't promise it yet.
7. **Workspace-scoped only.** `sculpt plugin …` runs inside a workspace and infers
   the workspace id (as `sculpt signal` infers the agent id from the env).
   Host-side use can come later.
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

This is the piece worth designing first; the L1/L2 question falls out of it.

`sculpt plugin load <target>` runs inside a workspace and infers the workspace id.
Behaviour depends on `<target>`:

### Path form — `sculpt plugin load ./my-plugin` (or `…/manifest.json`): dev loop

1. **Resolve** the `manifest.json`; read `id`, `entry`, and any referenced assets.
2. **Package** — gather the manifest + the entry bundle + referenced assets into a
   self-contained set. `load` does **not** build: the agent builds first (or writes
   a no-build plugin) and `load` packages whatever the manifest points at. (A
   `--build <cmd>` hook can come later.)
3. **Place** the package where the backend serves it, **nested by workspace** to
   avoid cross-workspace collisions:
   `~/.sculptor/plugins/<workspace-id>/<plugin-id>/`. Placement always goes
   **through a backend endpoint** (the CLI streams the packaged files to it), so:
   - it works whether or not the workspace shares the host filesystem (worktree vs
     container) — the backend writes the files;
   - the **agent-loading switch gates it server-side**, one code path;
   - nothing relies on the agent reaching the host home directly, even though it
     technically could.
4. **Trigger** load (or reload, if that id is already active) over the command
   channel, and **return the result** — `loaded` or `error{phase,message}` — over
   the return channel, so the CLI exits non-zero on a failed activate.

**Why this is L2, not L1:** the path form has to turn workspace files into
backend-served bytes; placing them in the existing `/plugins/local`-style store
reuses all SCU-1517 serving infrastructure and adds **no new executable-file
endpoint**. Live workspace-serving (L1) would add a serving surface for no real
gain now that placement is cheap and the switch is the gate.

### URL form — `sculpt plugin load https://…`: permanent install

Registers the URL as a **persistent url-source** (the same mechanism as a
user-added source; persisted in `pluginSourcesAtom` / localStorage), triggers the
load, returns the result. Survives restarts. No packaging or placement. This is
the "more permanent way to install a plugin."

### Persistence of path-form loads

Path-form (dev) loads are **command-driven**: the files stay on disk under the
workspace-nested dir, and the plugin is (re)loaded when the agent runs `load` /
`reload`. After a Sculptor restart the agent re-runs `load`. We deliberately do
**not** auto-register dev loads as persistent sources in v1 (see open questions).

### Workspace nesting vs passive discovery

Passive discovery (`GET /api/v1/plugins/local`) scans one level deep for **user
drop-ins** and stays as-is. Agent loads are **pushed imperatively** — the command
carries the exact manifest URL — so they need the static mount to serve the nested
`<ws-id>/<id>/` path but need not appear in passive discovery. (Open question:
whether `sculpt plugin list` should still surface agent-loaded plugins.)

## The bridge: command out + result back

Generalize UI Actions into a request/response with a correlation id. One mechanism
serves `load` / `reload` / `unload` **and** `inspect`:

1. CLI → `POST /api/v1/plugins/command` (workspace-scoped) with
   `{op, args, correlationId}`.
2. Backend `publish_ui_action(PluginCommandUiAction{op, args, correlationId})` over
   the WS.
3. The renderer handles it in `useUnifiedStream`, runs the matching `pluginManager`
   method, then POSTs the outcome to
   `POST /api/v1/plugins/command/{correlationId}/result`.
4. The backend correlates (a waiter keyed by `correlationId`, like a future) and
   returns the result to the still-blocked CLI request — or times out with a clear
   message: *"no Sculptor window responded — is it running with frontend plugins
   enabled?"*.

Multi-renderer is out of scope for v1 (Electron-first ⇒ one window). The backend
aggregates whatever results arrive (keyed by a per-page-load renderer id) and the
CLI shows them; with one window that's a single result.

## Inspect: what we report (and what we must not)

`sculpt plugin inspect <id>` (and `list`) collect, via the bridge, a **curated,
redacted** snapshot the renderer assembles explicitly — it never dumps localStorage
wholesale:

- **status** — `loaded | error{phase,message} | shadowed{activeSource} | disabled |
  missing`.
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

- `sculpt plugin load <path|url>` — path = package + place + load (dev loop); url =
  persistent install. Returns load result; non-zero exit on failure.
- `sculpt plugin reload [<id>|<path>]` — re-package (for path) + cache-bust reload.
- `sculpt plugin unload <id>` — unload (does not delete files).
- `sculpt plugin list` — discovered + agent-loaded plugins with live status.
- `sculpt plugin inspect <id>` — status, registrations, **redacted** config.
- `sculpt plugin dir` — print the data plugins dir (`/plugins/dir`).
- All: `--json` for agents; clear non-zero exits on "disabled / not connected /
  load failed".

## Phased implementation plan

1. **Bridge.** `PluginCommandUiAction` + `POST /api/v1/plugins/command` +
   correlation-id waiter + result endpoint; renderer handler in `useUnifiedStream`
   calling `pluginManager.load/reload/unload`. (Generalizes the open-file/webview
   pattern.)
2. **Agent-loading switch.** New `UserConfig` flag (closed default) + Settings
   toggle + server-side enforcement on the command endpoint.
3. **Packaging + placement (path form).** Endpoint that receives a packaged plugin
   and writes it to `~/.sculptor/plugins/<ws-id>/<id>/`; static mount serves the
   nested path; command fires the load and returns the result.
4. **URL form.** Persistent url-source registration via the command channel.
5. **Inspect.** Renderer assembles the redacted snapshot; CLI reads it via the
   bridge.
6. **CLI sub-app** wiring all of the above, with `--json`.
7. **Tests.** Mirror `test_plugin_loader.py` (flip both flags via config populator,
   drive via the CLI/endpoint, assert on the settings POM `data-status` /
   `data-phase` hooks). Electron-marked variant where it matters.

Later: browser support; multi-renderer `inspect`/`list`; host-side `sculpt`;
`--build` / `--watch`; auto-registering dev loads as persistent sources; auth on
the static routes.

## Remaining open questions

1. **Dev-load persistence** — keep path-form loads command-driven (re-run after
   restart), or auto-register them as persistent local sources so they reload on
   app restart? (Leaning command-driven for v1.)
2. **`list` scope** — should agent-loaded (workspace-nested) plugins appear in
   `sculpt plugin list` / passive discovery, or only when explicitly inspected?
3. **Packaging boundary** — confirm v1 expects a pre-built `entry` and never runs a
   build (agent builds first); `--build` is a later add.
4. **Switch naming** — name for the new sibling flag (e.g.
   `allow_agent_plugin_loading`).
