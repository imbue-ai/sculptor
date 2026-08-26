# Extension runtime stubs

The `/extension-runtime/*.js` stubs resolve the bare-specifier imports in
extension bundles (via the import map in `index.html`) to the host's singleton
instances, read from `window.__SCULPTOR_HOST__` (populated by
`src/extensions/hostRuntime.ts`).

**These files are generated, not checked in.** The `extensionRuntimeStubs` Vite
plugin (`vite-plugins/extension-runtime-stubs.ts`) derives each stub's export
list from the *actual* installed module namespace, serves them in dev, and emits
them into the build output — so an extension can import any name the host
package really exports, instead of a hand-curated subset that silently yielded
`undefined`.

To add a new shared package: add it to the import map in `index.html`, expose
its namespace on `window.__SCULPTOR_HOST__` in `hostRuntime.ts`, and add a
`RUNTIME_MODULES` entry (and, if its version should be embedded, a
`VERSION_PACKAGES` entry) in the Vite plugin. No stub file to maintain here.
