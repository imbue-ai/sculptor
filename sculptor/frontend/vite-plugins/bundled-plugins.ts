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
 * `linear-issue` is the only such plugin today; pure-JS plugins need no build
 * (their source is committed directly under `public/plugins/<id>/`). Wiring the
 * compile into the host build means `npm run build` and the dev server produce
 * the bundle — there's no separate `cd plugins/<id> && npm run build` step, and
 * no second toolchain: the plugin reuses the host's Vite, React, and TypeScript.
 *
 * Each bundle externalises exactly `RUNTIME_MODULE_SPECIFIERS` — the bare
 * specifiers the host's import map resolves to its singletons — so it carries
 * only the plugin's own code and shares the host's React, Radix, TanStack
 * Query, etc. at runtime.
 */

/** Plugins built from TS/TSX source at `plugins/<id>/src/index.tsx`. */
const COMPILED_PLUGIN_IDS: ReadonlyArray<string> = ["linear-issue"];

const buildCompiledPlugin = async (frontendRoot: string, id: string): Promise<void> => {
  const sourceDir = path.join(frontendRoot, "plugins", id);
  const outDir = path.join(frontendRoot, "public", "plugins", id);
  await build({
    configFile: false, // don't reload the host config — that would recurse
    root: sourceDir,
    publicDir: false,
    logLevel: "warn",
    // A compiled plugin is a production artifact: it shares the host's React
    // singleton via the import map, which provides only the prod
    // `react/jsx-runtime` (not `react/jsx-dev-runtime`). Pin production —
    // otherwise this nested build inherits the dev server's mode and the JSX
    // transform emits the dev runtime, which, not being externalized, gets
    // bundled in and drags `process.env.NODE_ENV` into a browser bundle
    // ("process is not defined"). The `define` is belt-and-suspenders: it
    // replaces any residual `process.env.NODE_ENV` so no `process` global can
    // reach the browser.
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
  // The manifest is served alongside the bundle; the host fetches it first.
  fs.copyFileSync(path.join(sourceDir, "manifest.json"), path.join(outDir, "manifest.json"));
};

export const bundledPlugins = (): Plugin => {
  let frontendRoot = process.cwd();
  let isBuild = false;

  const buildAll = async (): Promise<void> => {
    for (const id of COMPILED_PLUGIN_IDS) await buildCompiledPlugin(frontendRoot, id);
  };

  return {
    name: "sculptor:bundled-plugins",

    configResolved(config): void {
      frontendRoot = config.root;
      isBuild = config.command === "build";
    },

    // Production/CI build: emit into public/ before Vite copies it into the
    // output dir. Gated on the build command so the nested build above (which
    // runs without this plugin) can't recurse.
    async buildStart(): Promise<void> {
      if (isBuild) await buildAll();
    },

    // Dev server: build once at startup so `/plugins/<id>/main.js` is served
    // from public/, then rebuild on source edits.
    async configureServer(server): Promise<void> {
      await buildAll();
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
        void buildAll().finally(() => {
          isRebuilding = false;
        });
      });
    },
  };
};
