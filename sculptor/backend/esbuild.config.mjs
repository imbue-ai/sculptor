import { build } from "esbuild";

// Bundles the backend entrypoint into a single CommonJS file the pinned Node
// runtime runs directly. Native addons (better-sqlite3, node-pty) are
// externalized so they load from node_modules siblings of the bundle — bundling
// them breaks at runtime. Task 9.1 ships this bundle in the sidecar alongside a
// pinned Node 24 runtime (the addon ABI the justfile pins, not the doc's "20").
await build({
  entryPoints: ["src/index.ts"],
  outfile: "dist/backend.cjs",
  bundle: true,
  platform: "node",
  target: "node20",
  format: "cjs",
  sourcemap: true,
  external: ["better-sqlite3", "node-pty"],
});
