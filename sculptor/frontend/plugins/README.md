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
key and per-workspace pins through the plugin-settings SDK. It also contributes
a **workspace widget** (`registerWorkspaceWidget`) — a compact ticket chip the
host renders in the workspace banner beside the PR button. The widget defaults
to the branch ticket but follows whatever ticket the user assigns from the
panel; the two share a single per-workspace ticket-assignment setting, so the
ticket reference stays consistent across both surfaces.

![The Linear workspace widget — a "# SCU-1234" ticket chip — in the workspace banner](linear-issue/docs/workspace-widget.png)

It also registers a **home view** (`registerHomeView`) — a "Linear board" the
homepage offers in its view switcher — listing the current user's assigned
issues grouped by workflow state, with each ticket flagged by whether a Sculptor
workspace already exists for it (and a button into that workspace, via
`useNavigateToWorkspace`). The workspace↔ticket matching lives in one place
(`linear/association.ts`) shared with the panel, so the two surfaces agree on
which workspace is working which ticket.

It is structured as a
reference: a `linear/` core (Linear client, source-merging, query hooks) kept
separate from presentational `components/`, with `index.tsx` doing only
`activate()` wiring.

`preview-switcher` is a second compiled plugin, but deliberately NOT built-in:
it only makes sense behind the OpenHost nginx `/proxy` front (see
`openhost-nginx.conf` at the repo root), where it is installed as a *local*
plugin by dropping its built output into the backend's
`<sculptor-folder>/plugins/preview-switcher/`. It contributes an overlay
(`registerOverlay`) — a pill in the footer strip's empty bottom-left corner —
that lists the live Vite dev previews behind `/proxy/<port>/` and switches
between them and the deployed app, preserving the `#/` route. On a preview it
becomes an amber badge showing that preview's identity (the `sculptor-preview`
meta injected by `vite.base.config.ts`).

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
  and `preview-switcher` are the compiled plugins today; their
  `public/plugins/<id>/` output is gitignored.

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

The full contract is rolled up into
`sculptor/sculptor-plugin/skills/build-sculptor-plugin/sdk.d.ts` (generated —
`just generate-plugin-sdk-dts`, freshness-checked in CI), which ships to every
Sculptor agent inside the build-sculptor-plugin skill. Highlights:

- `useCurrentWorkspace(selector?)` — the active workspace as a curated view
  (`id`, `description`, `branch`, `targetBranch`, `pullRequestUrl`); pass a
  selector to subscribe to one field, e.g.
  `useCurrentWorkspace((w) => w?.branch ?? null)`.
- `useWorkspaces()` — every workspace as the same curated `WorkspaceView` shape
  `useCurrentWorkspace` returns (`id`, `description`, `branch`, `targetBranch`,
  `pullRequestUrl`), or `undefined` until the first batch loads. App-global, so
  it works in overlays and home views.
- `useNavigateToWorkspace()` — returns `(workspaceId) => void` that opens a
  workspace exactly as clicking it in the host's own lists does (opens or
  converts its tab, then jumps to its most-recently-used agent). The blessed way
  for a home view to send the user into a workspace.
- `useWorkspaceTasks()` — the workspace's tasks (host task data).
- `usePluginSetting(key)` — a persisted string setting scoped to the plugin
  (localStorage under `sculptor-plugin:<id>:<key>`), shared between the
  plugin's panel and its settings component.
- `usePluginSettings(keys)` — the multi-key companion: read many of the plugin's
  settings at once, reactively, returning a `Map<key, value>`. For when the key
  set is dynamic (e.g. one key per workspace from `useWorkspaces`), where you
  can't call `usePluginSetting` once per key.
- `Markdown` — the host's markdown renderer (`{ content: string }`); GFM,
  links open in a new tab, code blocks get copy buttons.
- `openExternal(url)` — open a URL in the user's browser (a new tab on the web;
  the system browser in the desktop app). Use this rather than `window.open`.
- `PanelHeader`, domain types, and the `PluginHostApi` / `PanelDefinition` /
  `WorkspaceWidgetDefinition` / `HomeViewDefinition` registration types (so
  plugins type `activate(api)` against the host contract instead of re-declaring
  it).

### Contribution points (`activate(api)`)

- `registerPanel(def)` — a panel in one of the workspace zones.
- `registerSettings(component)` — a settings section under the plugin.
- `registerOverlay(def)` — an always-on, app-global floating layer.
- `registerWorkspaceWidget(def)` — a compact, workspace-scoped widget the host
  places in its workspace chrome (today the banner's action row, beside the PR
  button). Like a panel it is mounted in the `WorkspacePluginContext`, so the
  workspace SDK hooks resolve to the workspace it is shown for. `collapsePriority`
  (lower = hidden first) slots it into the banner's progressive-collapse order;
  the host's own banner items occupy a few small integers. The name is
  placement-agnostic on purpose — the same registration is what a future
  per-workspace vertical-tabs layout would render.
- `registerHomeView(def)` — a full-page alternative homepage body. The homepage
  shows a view switcher whenever at least one is registered; picking one replaces
  the built-in recent-workspaces list with the plugin's component. The choice is
  remembered (per browser) and falls back to the built-in view if the plugin is
  unloaded. Like an overlay it is app-global (no `WorkspacePluginContext`), so it
  reads app state through the SDK hooks.

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
