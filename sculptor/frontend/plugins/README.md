# Frontend plugins (prototype)

This directory holds the source for runtime-loaded frontend plugins. Each
subdirectory is an independent Vite project that builds an ESM bundle into
the host's `public/plugins/<id>/` tree. The host loads built-in plugins plus
any user-added sources — see `src/plugins/pluginManager.tsx`.

No plugin ships bundled yet (`BUILTIN_SOURCES` is empty); this is the
scaffolding the first plugins will target. The whole system sits behind the
experimental **Frontend plugins** flag (Settings → Experimental): with the
flag off (the default) nothing loads and the Plugins settings section is
hidden from the sidebar and palette. Enabling the flag applies immediately
(plugins bootstrap and the section appears); disabling takes effect after an
app reload, since already-loaded plugins are not unloaded mid-session. The
section also stays reachable at `#/settings?section=PLUGINS` regardless of the
flag, for plugin development.

## How a plugin is built and loaded

1. Plugin source lives in `plugins/<id>/src/index.tsx`. Its `vite.config.ts`
   marks every shared dependency (`react`, `@radix-ui/themes`, `jotai`,
   `@tanstack/react-query`, `lucide-react`, `@sculptor/plugin-sdk`, etc.) as
   external, so the bundle contains only the plugin's own code.
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

- `useWorkspaceTasks()` — the workspace's tasks (host task data).
- `useWorkspaceId()`, `useWorkspaceBranch()` — workspace id / current branch.
- `usePluginSetting(key)` — a persisted string setting scoped to the plugin
  (localStorage under `sculptor-plugin:<id>:<key>`), shared between the
  plugin's panel and its settings component.
- `PanelHeader` and domain types.

## Caching fetched data (`@tanstack/react-query`)

Plugins may use `@tanstack/react-query` directly — it resolves through the
import map to the host's library and the host's **shared QueryClient** (plugin
components render under the host's provider). Cached data survives panel
close/reopen and workspace switches, and concurrent mounts dedupe to one
request. Rules:

- **Key namespace**: the first element of every query key MUST be your plugin
  id (e.g. `["my-plugin", "issue", id]`). The host's keys live under the
  reserved `"sculptor"` prefix. A dev-mode guard warns on keys outside either
  namespace.
- **Set `staleTime` explicitly**: the host's default is `Infinity` (its
  queries are invalidated by the WebSocket stream); without an override your
  data will never refetch.
- **Scope imperative calls to your namespace**: `invalidateQueries({ queryKey:
  ["<your-id>"] })` is fine; never call `clear()` or unfiltered
  `invalidateQueries()` — the cache is shared with the host.
- `QueryClient`/`QueryClientProvider` are intentionally not exported by the
  runtime stub: don't construct your own client, it would cut host components
  rendered inside your subtree off from the shared cache.
- Don't put secrets (API keys) in query keys — keys are visible in cache
  inspection/devtools. Close over them in the `queryFn` and invalidate your
  namespace when they change.

## Adding a plugin

1. Create `plugins/<id>/` — a small Vite project with a `manifest.json`
   (`id`, `name`, `version`, `entry`, `sdkVersion`) and a
   build that externalises the shared deps and outputs
   `public/plugins/<id>/main.js`.
2. Add `/plugins/<id>` to `BUILTIN_SOURCES` in `src/plugins/pluginManager.tsx`
   to bundle it, or add it as a source at runtime via the Plugins settings.
3. Build it once; the host picks it up on next reload.

## What's mocked vs. real

- The built-in plugin list is hardcoded; user sources are persisted to
  localStorage and managed from the Plugins settings.
- The SDK package is published as a runtime stub via the import map; it
  is not yet a separate npm package.
- `usePluginSetting` persists to localStorage in the renderer; it is not a
  secure secret store.
