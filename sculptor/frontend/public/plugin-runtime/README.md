# Plugin runtime stubs

These files are served at `/plugin-runtime/*` and resolve the bare-specifier
imports in plugin bundles via the import map declared in `index.html`. Each
stub re-exports the host's singleton instances from `window.__SCULPTOR_HOST__`,
which the host populates during boot (see `src/plugins/hostRuntime.ts`).

If you add a new shared package to the import map, add a stub file here that
mirrors the named exports that plugin code is expected to use.

TODO(SCU-1488): these stubs are hand-maintained re-export lists — a plugin
importing an un-enumerated name silently gets `undefined`. Generate them at
build time with a Vite plugin, from each shared package's actual module
namespace (plus the default-export escape hatch where one exists). That also
lets the loader enforce peer-dependency versions, which were dropped from the
manifest for now precisely because they couldn't be checked.
