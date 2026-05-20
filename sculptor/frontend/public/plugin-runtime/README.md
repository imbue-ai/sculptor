# Plugin runtime stubs

These files are served at `/plugin-runtime/*` and resolve the bare-specifier
imports in plugin bundles via the import map declared in `index.html`. Each
stub re-exports the host's singleton instances from `window.__SCULPTOR_HOST__`,
which the host populates during boot (see `src/plugins/hostRuntime.ts`).

If you add a new shared package to the import map, add a stub file here that
mirrors the named exports that plugin code is expected to use.
