---
name: build-sculptor-plugin
description: |
  Build or modify a Sculptor frontend plugin — a runtime ESM module loaded
  into the Sculptor UI. Use when asked to write a plugin, add a panel,
  overlay, workspace widget, home view, or settings UI to Sculptor, or to
  iterate on a plugin with `sculpt plugin`. Works from any repo; this file is
  a self-contained reference (the Sculptor source code is optional).
---

# Build a Sculptor plugin

A plugin is a runtime ES module the Sculptor frontend imports at load time. It
is **not** built into the app — it ships as its own files and is loaded live.
Everything you need is in this file plus the `sculpt` CLI; you do **not** need
the Sculptor source code or a dev build of Sculptor (see the last section for
when they help).

A plugin is a directory containing `manifest.json` plus an ESM entry module
that default-exports an `activate(api)` function.

Two files ship next to this SKILL.md (resolve them against this skill's base
directory):

- `sdk.d.ts` — the **authoritative, generated** contract of
  `@sculptor/plugin-sdk`: every hook, component, and registration option with
  its doc comments. Read it before writing plugin code; the prose below only
  summarizes it.
- `example/` — the quick-start plugin below as ready-to-load files (Sculptor's
  e2e tests load this exact directory, so it is known-good).

## Quick start (no build step)

```json
// manifest.json
{ "id": "hello", "name": "Hello", "version": "0.1.0", "entry": "main.js", "sdkVersion": "^1.0.0" }
```

```js
// main.js — hand-written ESM, imported directly by the host (no bundler)
export default function activate(api) {
  const el = document.createElement("div");
  el.textContent = "hello from a plugin";
  el.style.cssText = "position:fixed;bottom:16px;right:16px;pointer-events:auto;";
  document.body.appendChild(el);
  return () => el.remove(); // disposer — REQUIRED cleanup on unload/reload
}
```

```bash
sculpt plugin load <this-skill's-base-dir>/example   # package + load into the live UI
sculpt plugin inspect hello                          # see what it registered
```

## Prerequisites — the two settings toggles

Both live in **Settings → Plugins** in the Sculptor UI; only the user can flip
them:

- **Frontend plugins** (`enable_frontend_plugins`, default **on**) — master
  switch for the plugin runtime.
- **Agent plugin loading** (`allow_agent_plugin_loading`, default **off**) —
  gates the mutating CLI ops (`load`, `reload`, `unload`, `remove`).
  Read-only ops (`list`, `inspect`, `dir`) always work.

If a mutating command fails with HTTP 403 / `agent_plugin_loading_disabled`,
ask the user to enable "Agent plugin loading" under Settings → Plugins, then
retry. If no window responds at all, Sculptor isn't running or frontend
plugins are disabled.

## Dev loop — `sculpt plugin`

(See the `sculpt-cli` skill for general `sculpt` usage; all commands accept
`--json` and infer the workspace from `SCULPT_WORKSPACE_ID`.)

| Command | What it does |
|---|---|
| `sculpt plugin load <dir\|manifest.json\|url> [--persist]` | Package the directory (or register the URL) and load it into the live UI |
| `sculpt plugin reload <id>` | Re-package (if from a path) and re-fetch with cache-busting — run after every edit |
| `sculpt plugin inspect <id>` | One plugin's live status, registrations, and config **key names** (values are never shown) |
| `sculpt plugin list` | All plugins (builtin / installed / url / dev) with live status per window |
| `sculpt plugin unload <id>` | Unload from the UI; files stay on disk |
| `sculpt plugin remove <id>` | Unload + delete the workspace's dev install (idempotent; leaves permanent installs alone) |
| `sculpt plugin dir` | Print the backend's plugins directory (e.g. `~/.sculptor/plugins`) |

`load` mechanics worth knowing:

- A local path is packaged and uploaded (dotfiles, `node_modules`, and
  `__pycache__` are skipped; 5 MB encoded limit) to a **workspace-scoped dev
  install** at `<plugins-dir>/dev/<workspace-id>/<plugin-id>/`. Re-loading
  wipes and rewrites that directory.
- `--persist` installs to the top-level `<plugins-dir>/<plugin-id>/` instead —
  a permanent install that survives after this workspace is gone. URLs are
  always persistent sources; `--persist` has no effect on them.
- The plugin `id` must be a single safe path segment: no `/` or `\`, not
  exactly `.` or `..` (dots inside an id like `foo.bar` are fine), and not the
  reserved name `dev`.
- `load` and `reload` wait for the plugin to **settle**: `load: OK` means it
  reached `status: loaded` (manifest fetched, validated, imported, activated).
  A failure at any phase (`manifest`, `validate`, `import`, `activate`, or the
  catch-all `load`) prints
  `load: FAILED` with the phase and error message and exits non-zero. Errors
  thrown *after* activation (e.g. inside a component render) surface in the
  UI's per-plugin error boundary instead — check `inspect` and the UI when
  something registered but doesn't render.

Typical loop: `load` → edit → `reload` → … → `remove` (cleanup) or
`load --persist` (keep it installed).

Manual no-CLI route: drop the plugin directory into
`<plugins-dir>/<plugin-id>/` (path from `sculpt plugin dir`) and click the
**Refresh** button in Settings → Plugins.

## manifest.json

All five fields are required non-empty strings; there are no optional fields:

| Field | Meaning |
|---|---|
| `id` | Stable identifier — used in CLI commands, registration namespaces, and the settings localStorage prefix. Safe path segment, not `dev`. |
| `name` | Display name in Settings → Plugins |
| `version` | Informational; shown in the UI, not validated |
| `entry` | ESM entry file, relative to the manifest |
| `sdkVersion` | Semver range; only the **major** must match the host's SDK major, which is `1` — use `"^1.0.0"` |

## The entry module — `activate` and disposers

```ts
type PluginActivate = (api: PluginHostApi) => void | (() => void) | Promise<void | (() => void)>;
```

- The host imports the entry and calls its **default export** with the API.
- Return a **disposer** that undoes every module-level side effect (DOM nodes,
  event listeners, timers, injected `<style>` tags). Disposers must be
  synchronous. Registrations made through `api.register*` each return their
  own undo function — compose them into the disposer you return.
- If `activate` throws or rejects, the plugin lands in `error` status with
  phase `activate`, any registrations it already made are rolled back, and
  other plugins are unaffected.
- On reload the disposer runs, then the module is re-imported (cache-busted)
  and re-activated.

## The host API and SDK — read `sdk.d.ts`

The full typed contract — `PluginHostApi`, every registration option shape,
every hook signature, and their doc comments — is in the generated **`sdk.d.ts`
next to this file**. It is authoritative; read it rather than trusting any
summary. What it contains, in one breath:

- `api.registerPanel` / `registerSettings` / `registerOverlay` /
  `registerWorkspaceWidget` / `registerHomeView` — each returns an undo
  function; registering twice with the same `id` replaces the previous
  contribution; every component renders inside a per-plugin error boundary and
  receives **no props**.
- Hooks: `useCurrentWorkspace` (selector form available), `useWorkspaces`,
  `useWorkspaceTasks`, `useNavigateToWorkspace`, `usePluginSetting`,
  `usePluginSettings`.
- Components and actions: `Markdown`, `PanelHeader`, `openExternal`.

Semantics that matter beyond the types:

- **Workspace scope**: panels and workspace widgets are mounted per-workspace,
  so workspace-scoped hooks work directly. Overlays, home views, and settings
  components are app-global — `useWorkspaceTasks` is unavailable there, and
  `useCurrentWorkspace` reflects whichever workspace the current route shows
  (or `null`).
- **Overlays** render in a `pointer-events: none` layer — interactive elements
  must set `pointer-events: auto` themselves.
- **`usePluginSetting`** persists per-plugin strings in localStorage
  (`sculptor-plugin:<id>:<key>`). Values are **plaintext** — treat anything
  the user puts there (e.g. an API token) as visible to anyone with devtools
  access, and JSON-encode yourself if you need structure.
- Prefer the selector form of `useCurrentWorkspace`
  (e.g. `(w) => w?.branch ?? null`) to avoid re-rendering on unrelated
  workspace changes.

### Host-provided modules — never bundle these

The host import map provides exactly these bare specifiers; mark them as
externals in any build, and never ship your own copy (a second React instance
breaks hooks):

```
react   react/jsx-runtime   react-dom   react-dom/client
jotai   @tanstack/react-query   @radix-ui/themes   lucide-react
@sculptor/plugin-sdk
```

Notes: `@tanstack/react-query` deliberately does not expose `QueryClient` /
`QueryClientProvider` — plugins share the host's query cache; namespace your
query keys with your plugin id (e.g. `["my-plugin", "issue", id]`). Importing
a name a module doesn't export silently yields `undefined` at runtime, so
verify in the UI rather than trusting the build.

## Two flavors: no-build vs. built

**No-build** (start here): hand-written ESM. Raw DOM (as in the quick start),
or React without JSX via `createElement`:

```js
import { createElement as h, useState } from "react";
import { usePluginSetting } from "@sculptor/plugin-sdk";

const Badge = () => {
  const [label, setLabel] = usePluginSetting("label");
  return h("div", { style: { pointerEvents: "auto", position: "fixed", top: 8, right: 8 } },
    h("input", { value: label, onChange: (e) => setLabel(e.target.value) }));
};

export default function activate(api) {
  return api.registerOverlay({ id: "badge", component: Badge });
}
```

**Built** (when you want JSX/TypeScript/dependencies): any bundler that emits
a single ESM file with the host modules external. Minimal Vite setup:

```ts
// vite.config.ts — devDependencies: vite, @vitejs/plugin-react
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  define: { "process.env.NODE_ENV": JSON.stringify("production") },
  build: {
    lib: { entry: "src/index.tsx", formats: ["es"], fileName: () => "main.js" },
    rollupOptions: {
      external: [
        "react", "react/jsx-runtime", "react-dom", "react-dom/client",
        "jotai", "@tanstack/react-query", "@radix-ui/themes", "lucide-react",
        "@sculptor/plugin-sdk",
      ],
    },
  },
});
```

The SDK is not published to npm. For TypeScript, copy the `sdk.d.ts` shipped
next to this skill into your project and alias it in `tsconfig.json`:
`"paths": { "@sculptor/plugin-sdk": ["./sdk.d.ts"] }` (you'll want
`@types/react` installed for full fidelity). After building, place
`manifest.json` next to the bundle (`"entry": "main.js"`) and
`sculpt plugin load <dist-dir>` — loading the output directory keeps the
upload small.

## Gotchas

- `load`/`reload` report the settled status, but errors thrown after
  activation (event handlers, component renders) don't reach the CLI — when
  something registered but misbehaves, check `inspect` and the UI's plugin
  error boundary.
- Disposers are synchronous; clean up injected styles/listeners/timers, not
  just DOM nodes.
- Overlays: remember `pointer-events: auto` on interactive elements.
- Settings are plaintext localStorage; `inspect` reports key names only.
- Use Radix theme CSS variables (e.g. `var(--gray-12)`, `var(--accent-9)`)
  so the plugin follows the host theme, and `@radix-ui/themes` components
  for native-feeling UI.
- One plugin id wins per source priority (local > url > builtin); a shadowed
  duplicate loads its manifest but never activates.

## Going deeper with the Sculptor source (optional)

None of this is required — the contract above is complete — but if you have a
checkout of [github.com/imbue-ai/sculptor](https://github.com/imbue-ai/sculptor)
(or are already working in it), you can go deeper:

- **SDK source**: `sculptor/frontend/src/plugins/types.ts` (host API
  contract) and `sculptor/frontend/src/plugins/sdk/` (hooks, components,
  actions) — the `sdk.d.ts` next to this skill is generated from these
  (`just generate-plugin-sdk-dts`).
- **Reference plugins**: `sculptor/frontend/public/plugins/sculpty/`
  (no-build raw DOM), `sculptor/frontend/public/plugins/pomodoro/` (no-build
  React overlay with persisted settings), and
  `sculptor/frontend/plugins/linear-issue/` (full TypeScript/Vite panel +
  settings + widget + home view).
- **Bundled plugins**: plugins shipped with the app are built by the host's
  Vite config (`sculptor/frontend/vite-plugins/bundled-plugins.ts`); adding an
  id to `COMPILED_PLUGIN_IDS` there builds `plugins/<id>/src/` automatically.
- **In-repo skills**: when working inside the Sculptor repo you can run a dev
  build of the app and use the `auto-qa-changes` skill to drive the UI in a
  headless browser for visual verification, instead of relying on the user's
  live instance.
