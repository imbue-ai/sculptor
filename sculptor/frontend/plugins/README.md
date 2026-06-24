# Frontend plugins (prototype)

This directory holds the source for runtime-loaded frontend plugins. Each
subdirectory is an independent Vite project that builds an ESM bundle into
the host's `public/plugins/<id>/` tree. The host loads built-in plugins plus
any user-added sources — see `src/plugins/pluginManager.tsx`.

The whole system sits behind the experimental **Frontend plugins** flag
(Settings → Experimental): with the flag off (the default) nothing loads and
the Plugins settings section is hidden from the sidebar and palette. Enabling
the flag applies immediately (plugins bootstrap and the section appears);
disabling takes effect after an app reload, since already-loaded plugins are
not unloaded mid-session. The section also stays reachable at
`#/settings?section=PLUGINS` regardless of the flag, for plugin development.

The bundled example is `linear-issue`. It shows the Linear issues linked to a
workspace as collapsible sections, each tagged with where it came from: the
branch's issue (primary — `issueVcsBranchSearch`, then an identifier parsed from
the branch name, then the workspace's PR resolved via `attachmentsForURL`, so
Sculptor-generated branches that Linear has no link for still resolve), the
issues that issue's PR links to (`attachmentsForURL`), and any the user pins via
a quick-search box (`searchIssues`). It renders descriptions with the
SDK `Markdown` component, opens links via `openExternal`, and stores its API
key and per-workspace pins through the plugin-settings SDK. It is structured as
a reference: a `linear/` core (Linear client, source-merging, query hooks) kept
separate from presentational `components/`, with `index.tsx` doing only
`activate()` wiring.

## How a plugin is built and loaded

A plugin is loaded from `public/plugins/<id>/` (a `manifest.json` next to a
`main.js` ESM bundle). There are two ways that tree gets populated:

- **Pure-JS plugins** commit their `main.js` + `manifest.json` directly under
  `public/plugins/<id>/` — no build step.
- **Compiled plugins** keep TS/TSX source under `plugins/<id>/src/` and are
  built into `public/plugins/<id>/` by the host Vite build (see
  `vite-plugins/bundled-plugins.ts`), so `npm run build` and the dev server
  emit the bundle — there's no separate per-plugin build to run, and no second
  toolchain (the plugin reuses the host's Vite/React/TypeScript). `linear-issue`
  is the only compiled plugin today; its `public/plugins/linear-issue/` output
  is gitignored.

The build marks every shared dependency (`react`, `@radix-ui/themes`, `jotai`,
`@tanstack/react-query`, `lucide-react`, `@sculptor/plugin-sdk`, …) external —
the exact set the import map provides, derived from `RUNTIME_MODULE_SPECIFIERS`
— so the bundle contains only the plugin's own code. Then, at load time:

1. The host fetches `/plugins/<id>/manifest.json`, validates the
   declared SDK major against its own, then dynamic-imports `main.js`.
2. The plugin bundle's bare-specifier imports (`react`, etc.) resolve via
   the import map declared in `index.html` to runtime stubs under
   `/plugin-runtime/`, which re-export from `window.__SCULPTOR_HOST__` —
   the host's actual singleton instances.
3. The plugin's default export is an `activate(api)` function that calls
   `api.registerPanel({ ... })` and optionally `api.registerSettings(...)`.
   The host wraps contributed components in a `PluginErrorBoundary`, a
   `PluginContext` (plugin id, for `usePluginSetting`), and — for panels —
   a `WorkspacePluginContext` provider.

## SDK surface plugins target (`@sculptor/plugin-sdk`)

- `useCurrentWorkspace(selector?)` — the active workspace as a curated view
  (`id`, `description`, `branch`, `targetBranch`, `pullRequestUrl`); pass a
  selector to subscribe to one field, e.g.
  `useCurrentWorkspace((w) => w?.branch ?? null)`.
- `useWorkspaces()` — every workspace (app-global; works in overlays).
- `useWorkspaceTasks()` — the workspace's tasks (host task data).
- `usePluginSetting(key)` — a persisted string setting scoped to the plugin
  (localStorage under `sculptor-plugin:<id>:<key>`), shared between the
  plugin's panel and its settings component.
- `Markdown` — the host's markdown renderer (`{ content: string }`); GFM,
  links open in a new tab, code blocks get copy buttons.
- `openExternal(url)` — open a URL in the user's browser (a new tab on the web;
  the system browser in the desktop app). Use this rather than `window.open`.
- `PanelHeader`, domain types, and the `PluginHostApi` / `PanelDefinition`
  registration types (so plugins type `activate(api)` against the host
  contract instead of re-declaring it).

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
- **Scope imperative calls to your namespace**:
  `invalidateQueries({ queryKey: ["<your-id>"] })` is fine; never call
  `clear()` or unfiltered `invalidateQueries()` — the cache is shared with the
  host.
- `QueryClient`/`QueryClientProvider` are intentionally not exported by the
  runtime stub: don't construct your own client, it would cut host components
  rendered inside your subtree off from the shared cache.
- Don't put secrets (API keys) in query keys — keys are visible in cache
  inspection/devtools. Close over them in the `queryFn` and invalidate your
  namespace when they change.

## Adding a plugin

1. Author the plugin. For a pure-JS plugin, commit `main.js` + `manifest.json`
   (`id`, `name`, `version`, `entry`, `sdkVersion`) under `public/plugins/<id>/`.
   For a compiled (TS/TSX) plugin, put source under `plugins/<id>/src/` with a
   `manifest.json` and a `tsconfig.json`, then add its id to `COMPILED_PLUGIN_IDS`
   in `vite-plugins/bundled-plugins.ts` so the host build emits its bundle.
2. Add `/plugins/<id>` to `BUILTIN_SOURCES` in `src/plugins/pluginManager.tsx`
   to ship it built-in, or add it as a source at runtime via the Plugins settings.
3. The host build (or dev server) produces the bundle; the host picks it up on
   next reload.

## What's mocked vs. real

- The built-in plugin list is hardcoded; user sources are persisted to
  localStorage and managed from the Plugins settings.
- The SDK package is published as a runtime stub via the import map; it
  is not yet a separate npm package.
- `usePluginSetting` persists to localStorage in the renderer; it is not a
  secure secret store.
