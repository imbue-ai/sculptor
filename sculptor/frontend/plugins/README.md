# Frontend plugins (prototype)

This directory holds the source for runtime-loaded frontend plugins. Each
subdirectory is an independent Vite project that builds an ESM bundle into
the host's `public/plugins/<id>/` tree. The host loads built-in plugins plus
any user-added sources (see Settings → Plugins) — see `src/plugins/pluginManager.tsx`.

The example plugin is `linear-issue`: it reads the workspace branch via the
SDK, parses a Linear ticket id out of it, fetches that issue from Linear's
GraphQL API, and stores its API key through the plugin-settings SDK.

## How a plugin is built and loaded

1. Plugin source lives in `plugins/<id>/src/index.tsx`. Its `vite.config.ts`
   marks every shared dependency (`react`, `@radix-ui/themes`, `jotai`,
   `lucide-react`, `@sculptor/plugin-sdk`, etc.) as external, so the
   bundle contains only the plugin's own code.
2. `cd plugins/<id> && npm install && npm run build` emits
   `public/plugins/<id>/main.js` and copies `manifest.json` alongside it.
3. At runtime the host fetches `/plugins/<id>/manifest.json`, validates the
   declared SDK major against its own, then dynamic-imports `main.js`.
4. The plugin bundle's bare-specifier imports (`react`, etc.) resolve via
   the import map declared in `index.html` to runtime stubs under
   `/plugin-runtime/`, which re-export from `window.__SCULPTOR_HOST__` —
   the host's actual singleton instances.
5. The plugin's default export is an `activate(api)` function that calls
   `api.registerPanel({ ... })` and optionally `api.registerSettings(...)`.
   The host wraps contributed components in a `PluginErrorBoundary`, a
   `PluginContext` (plugin id, for `usePluginSetting`), and — for panels —
   a `WorkspacePluginContext` provider.

## SDK surface plugins target (`@sculptor/plugin-sdk`)

- `useWorkspaceTasks()`, `useTaskArtifact(taskId, type)` — read host task data.
- `useWorkspaceId()`, `useWorkspaceBranch()` — workspace id / current branch.
- `usePluginSetting(key)` — a persisted string setting scoped to the plugin
  (localStorage under `sculptor-plugin:<id>:<key>`), shared between the
  plugin's panel and its settings component.
- `PanelHeader`, `ArtifactType`, and domain types.

## Adding a new plugin to the loader

1. Create `plugins/<id>/` with the same shape as `linear-issue/`.
2. Add `/plugins/<id>` to `BUILTIN_SOURCES` in `src/plugins/pluginManager.tsx`
   (or just add it as a source at runtime via Settings → Plugins).
3. Build it once; the host picks it up on next reload.

## What's mocked vs. real

- `useTaskArtifact` is a hand-rolled fetch-on-mount that writes back to
  the existing `taskDetailAtomFamily`. It will move to TanStack Query and
  the public hook signature won't change.
- The built-in plugin list is hardcoded; user sources are persisted to
  localStorage and managed from Settings → Plugins.
- The SDK package is published as a runtime stub via the import map; it
  is not yet a separate npm package.
- `usePluginSetting` persists to localStorage in the renderer; it is not a
  secure secret store. The Linear API key lives there in plaintext.
