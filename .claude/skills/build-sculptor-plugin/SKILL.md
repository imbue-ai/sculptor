---
name: build-sculptor-plugin
description: |
  Build or modify a Sculptor frontend plugin — a runtime ESM module loaded into
  the Sculptor UI. Use when asked to write a plugin, add a panel/overlay/setting
  to the UI via a plugin, or iterate on one with `sculpt plugin`.
---

# Build a Sculptor plugin

> Minimal starting point (SCU-1520). The authoritative references are the
> example plugins and the SDK source linked below — read them; this file only
> orients you.

A plugin is a runtime ES module the Sculptor frontend imports at load time. It
is **not** built into the app — it ships as its own files and is loaded live. A
plugin is a directory with:

- `manifest.json` — `{ id, name, version, entry, sdkVersion }` (entry is the ESM
  file, relative to the manifest; host SDK major is `1`, so use `"^1.0.0"`).
- the entry module — default-exports `activate(api)`, which contributes to the
  UI and **returns a disposer** that tears everything down on unload/reload.

## Minimal example (no build step)

```json
// manifest.json
{ "id": "hello", "name": "Hello", "version": "0.1.0", "entry": "main.js", "sdkVersion": "^1.0.0" }
```

```js
// main.js — hand-written ESM, imported directly (no bundler)
export default function activate(/* api */) {
  const el = document.createElement("div");
  el.textContent = "hello from a plugin";
  document.body.appendChild(el);
  return () => el.remove(); // disposer
}
```

## The SDK

Plugins bare-import `@sculptor/plugin-sdk`; the host resolves it at runtime via
an import map (so `react`, `jotai`, etc. resolve to the host's own singletons —
do not bundle them). Key surface (see `sculptor/frontend/src/plugins/sdk/index.ts`):

- `api.registerPanel`, `api.registerSettings`, `api.registerOverlay` — each
  returns an undo function (the full contract is `PluginHostApi` in
  `sculptor/frontend/src/plugins/types.ts`).
- hooks: `useCurrentWorkspace`, `useWorkspaces`, `useWorkspaceTasks`,
  `usePluginSetting` (per-plugin persisted string — treat as plaintext).
- `Markdown`, `PanelHeader`, `openExternal`.

**Two flavors:** no-build (hand-written ESM, raw DOM or React via
`createElement`) or a Vite project that bundles to a single `main.js`. Start
no-build unless you need JSX/dependencies.

## Reference plugins — read these first

- `sculptor/frontend/public/plugins/sculpty/` — no-build, raw DOM.
- `sculptor/frontend/public/plugins/pomodoro/` — no-build React (`createElement`,
  `registerOverlay`, `usePluginSetting`).
- `sculptor/frontend/plugins/linear-issue/` — a built (Vite) plugin with a panel.

## Dev loop (iterate live)

The agent dev loop is gated by two toggles in **Settings → Plugins**: "Frontend
plugins" (`enable_frontend_plugins`, on by default — the feature) and "Agent
plugin loading" (`allow_agent_plugin_loading`, off by default — lets agents load
plugins via `sculpt`). Turn on "Agent plugin loading" for the dev loop; the same
section also lists the loaded plugins.

- `sculpt plugin load <dir>` — package + load your plugin into the live UI.
- `sculpt plugin reload <id>` — re-fetch after edits.
- `sculpt plugin inspect <id>` / `sculpt plugin list` — status + what it registered.
- `sculpt plugin remove <id>` — unload and delete the dev copy when done.

(See the `sculptor:sculpt-cli` skill for `sculpt` details.) Without the CLI, you
can also drop a plugin directory into `~/.sculptor/plugins/<id>/` and use the
**Refresh** button in Settings → Plugins.
