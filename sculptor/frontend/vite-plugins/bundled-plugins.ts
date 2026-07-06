import fs from "node:fs";
import path from "node:path";

import react from "@vitejs/plugin-react-swc";
import { build, type Plugin } from "vite";

import { RUNTIME_MODULE_SPECIFIERS } from "./plugin-runtime-stubs.ts";

/**
 * Builds the frontend plugins whose source is TypeScript/TSX (and so needs
 * compiling) as part of the host build, emitting each bundle into
 * `public/plugins/<id>/` — the same tree the no-build, pure-JS plugins live in.
 *
 * Pure-JS plugins need no build (their source is committed directly under
 * `public/plugins/<id>/`). Wiring the compile into the host build means
 * `npm run build` and the dev server produce the bundle — there's no separate
 * `cd plugins/<id> && npm run build` step, and no second toolchain: the plugin
 * reuses the host's Vite, React, and TypeScript.
 *
 * Each bundle externalises exactly `RUNTIME_MODULE_SPECIFIERS` — the bare
 * specifiers the host's import map resolves to its singletons — so it carries
 * only the plugin's own code and shares the host's React, Radix, TanStack
 * Query, etc. at runtime.
 */

/** Plugins built from TS/TSX source at `plugins/<id>/src/index.tsx`. */
const COMPILED_PLUGIN_IDS: ReadonlyArray<string> = ["linear-issue", "openhost-preview-switcher"];

const buildCompiledPlugin = async (frontendRoot: string, id: string): Promise<void> => {
  const sourceDir = path.join(frontendRoot, "plugins", id);
  const outDir = path.join(frontendRoot, "public", "plugins", id);
  // A compiled plugin is a production artifact: it shares the host's React
  // singleton via the import map, which provides only the prod
  // `react/jsx-runtime` (not `react/jsx-dev-runtime`). It MUST build as
  // production, or the JSX transform emits the dev runtime and plugin renders
  // crash with "jsxDEV is not a function" (and a bundled dev runtime would also
  // drag `process` in).
  //
  // Vite derives `isProduction` from `process.env.NODE_ENV || mode`, so NODE_ENV
  // *wins* over our `mode: "production"`. In the dev-server path (`just start`,
  // electron dev) the outer server sets NODE_ENV=development, which would force
  // this nested build to dev despite `mode`. Pin NODE_ENV for the build so it's
  // production in every path; restore it afterward so the outer dev server is
  // unaffected. `mode` + the `define` are kept as defense-in-depth.
  const priorNodeEnv = process.env.NODE_ENV;
  process.env.NODE_ENV = "production";
  try {
    await build({
      configFile: false, // don't reload the host config — that would recurse
      root: sourceDir,
      publicDir: false,
      logLevel: "warn",
      mode: "production",
      define: { "process.env.NODE_ENV": JSON.stringify("production") },
      plugins: [react()],
      build: {
        outDir,
        emptyOutDir: true,
        sourcemap: true,
        lib: {
          entry: path.join(sourceDir, "src", "index.tsx"),
          formats: ["es"],
          fileName: (): string => "main.js",
        },
        rollupOptions: {
          external: [...RUNTIME_MODULE_SPECIFIERS],
          // Don't hash — the manifest references the entry as "main.js" by name.
          output: { entryFileNames: "main.js", assetFileNames: "[name][extname]" },
        },
      },
    });
  } finally {
    if (priorNodeEnv === undefined) {
      delete process.env.NODE_ENV;
    } else {
      process.env.NODE_ENV = priorNodeEnv;
    }
  }

  // Fail loudly if the production pin above ever regresses: a dev JSX transform
  // emits `jsxDEV` / imports `react/jsx-dev-runtime`, which the host import map
  // doesn't provide, so the plugin would crash at render with
  // `s.jsxDEV is not a function`. Cheaper than waiting for the integration test.
  const bundle = fs.readFileSync(path.join(outDir, "main.js"), "utf8");
  if (bundle.includes("jsxDEV")) {
    throw new Error(
      `Plugin "${id}" was built with React's dev JSX transform (found "jsxDEV"). ` +
        `The host provides only the production "react/jsx-runtime", so this would crash at render. ` +
        `The production pin in bundled-plugins.ts is not taking effect — check NODE_ENV handling.`,
    );
  }

  // The manifest is served alongside the bundle; the host fetches it first.
  fs.copyFileSync(path.join(sourceDir, "manifest.json"), path.join(outDir, "manifest.json"));
};

export const bundledPlugins = (): Plugin => {
  let frontendRoot = process.cwd();
  let isBuild = false;
  // The startup build is memoized so it runs exactly once even if configResolved
  // fires more than once (e.g. worker config resolution): two overlapping
  // `emptyOutDir` rebuilds of the same dir would clobber each other.
  let startupBuild: Promise<void> | null = null;

  const buildAll = async (): Promise<void> => {
    for (const id of COMPILED_PLUGIN_IDS) await buildCompiledPlugin(frontendRoot, id);
  };
  const buildAllOnce = (): Promise<void> => (startupBuild ??= buildAll());

  return {
    name: "sculptor:bundled-plugins",

    // Build the dev-server bundles HERE, during config resolution — a hook Vite
    // awaits (before it creates the server) — so `public/plugins/<id>/main.js`
    // exists before the dev server snapshots the public directory
    // (`initPublicFiles`) into the set its static-file middleware serves from.
    //
    // Building later (in configureServer, which runs *after* that snapshot)
    // races it: the nested build's `emptyOutDir` unlinks each `main.js` and the
    // rewrite's `add` fires before Vite's public-dir watcher is attached, so the
    // freshly-built bundle is missing from the served set. Requests for it then
    // fall through to the SPA fallback (index.html); the browser rejects that
    // HTML as an ES module and the plugin's dynamic import fails ("failed:
    // import"). Only one bundle typically loses the race, and it never recovers
    // (a later `change` event doesn't re-add a path the snapshot missed).
    //
    // A production `vite build` copies the whole public dir with no such
    // snapshot, so its build stays in buildStart, gated off the serve path here.
    async configResolved(config): Promise<void> {
      frontendRoot = config.root;
      isBuild = config.command === "build";
      if (!isBuild) await buildAllOnce();
    },

    // Production/CI build: emit into public/ before Vite copies it into the
    // output dir. Gated on the build command so the nested build above (which
    // runs without this plugin) can't recurse.
    async buildStart(): Promise<void> {
      if (isBuild) await buildAllOnce();
    },

    // Dev server: the bundles were already built in configResolved (before the
    // public-files snapshot); here we only watch source edits and rebuild.
    async configureServer(server): Promise<void> {
      // Integration tests serve a prebuilt dist, not this dev server, so the
      // watcher is pure developer convenience and unnecessary under pytest.
      if (process.env.PYTEST_CURRENT_TEST) return;
      const sourceRoot = path.join(frontendRoot, "plugins");
      let isRebuilding = false;
      // Only "change": chokidar emits "add" for every existing file when a path
      // is first watched, which would trigger a redundant rebuild at startup.
      // A new source file is rare and picked up on the next edit or restart.
      server.watcher.on("change", (file: string): void => {
        if (!file.startsWith(sourceRoot) || isRebuilding) return;
        isRebuilding = true;
        void buildAll()
          // A failed rebuild (a broken edit, a file missing mid-rename) must
          // not crash the dev server as an unhandled rejection — log it and
          // keep serving; the next change retries.
          .catch((error: unknown) => {
            server.config.logger.error(`bundled-plugins: plugin rebuild failed: ${String(error)}`);
          })
          .finally(() => {
            isRebuilding = false;
          });
      });
    },
  };
};
