# Frontend plugins (prototype)

This directory holds the source for runtime-loaded frontend plugins. Each
subdirectory is an independent Vite project that builds an ESM bundle into
the host's `public/plugins/<id>/` tree. The host loads it at boot via a
hardcoded URL list in `src/plugins/PluginLoader.tsx`.

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
   `api.registerPanel({ ... })`. The host wraps the contributed component
   in a `PluginErrorBoundary` plus a `WorkspacePluginContext` provider
   before merging it into the panel registry.

## Adding a new plugin to the loader

1. Create `plugins/<id>/` with the same shape as `workspace-cost-tracker/`.
2. Add the plugin's manifest URL to `BUILTIN_PLUGIN_MANIFEST_URLS` in
   `src/plugins/PluginLoader.tsx`.
3. Build it once; the host picks it up on next reload.

## What's mocked vs. real

- `useTaskArtifact` is a hand-rolled fetch-on-mount that writes back to
  the existing `taskDetailAtomFamily`. It will move to TanStack Query and
  the public hook signature won't change.
- The plugin list is hardcoded; there is no enable/disable UI yet.
- The SDK package is published as a runtime stub via the import map; it
  is not yet a separate npm package.
