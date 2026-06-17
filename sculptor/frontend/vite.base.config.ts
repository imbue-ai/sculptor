// Shared Vite configuration for both frontend builds, so each bundles the app
// through the same plugin pipeline. Only the genuinely
// target-specific knobs are left to each entry config:
//
//   - vite.web.config.ts      (web / OpenHost):  base "/",  outDir dist,
//                                                 API_URL_BASE "" (same-origin)
//   - vite.renderer.config.ts (Electron renderer): base "./", outDir
//                                                 .vite/build/renderer,
//                                                 API_URL_BASE undefined
//                                                 (preload injects the port)
//
// Each entry config passes its own `root` (the frontend dir) so path resolution
// here never depends on how Vite bundles this module.
import fs from "node:fs";
import path from "node:path";

import react from "@vitejs/plugin-react-swc";
import type { Plugin } from "vite";

/**
 * Exclude ``@xterm/xterm`` from the bundle and serve it as a standalone
 * ES module that the browser loads directly.
 *
 * xterm.js v6 ships a pre-minified ESM bundle (``lib/xterm.mjs``) whose
 * TypeScript ``const enum`` patterns break when esbuild re-minifies them:
 * esbuild removes ``let`` declarations it considers dead, turning
 * ``r ||= {}`` into a reference to an undeclared variable that throws
 * ``ReferenceError`` in strict mode (ES modules).  The most visible symptom
 * is neovim failing to render — xterm's write buffer dies permanently.
 *
 * Instead of patching the source, we keep xterm out of the bundle entirely:
 *
 * 1. Mark ``@xterm/xterm`` as Rollup-external so it is never processed by
 *    Rollup or esbuild.
 * 2. Use ``output.paths`` to rewrite the import specifier to a relative URL
 *    (``./vendor/xterm.mjs``) that the browser fetches as a native ES module.
 * 3. Copy the original ``xterm.mjs`` into the output directory at build time.
 *
 * The file is served as-is — its ``let`` declarations survive because no
 * minifier ever touches it.
 *
 * Sub-path imports (e.g. ``@xterm/xterm/css/xterm.css``) are *not*
 * externalized and continue through Vite's normal CSS pipeline.
 */
export function externalizeXterm(root: string): Plugin {
  return {
    name: "externalize-xterm",
    config(): { build: import("vite").BuildOptions } {
      return {
        build: {
          rollupOptions: {
            external: (id: string): boolean => id === "@xterm/xterm",
            output: {
              paths: { "@xterm/xterm": "./vendor/xterm.mjs" },
            },
          },
        },
      };
    },
    writeBundle(options: { dir?: string }): void {
      // The bundled JS lives in <outDir>/assets/, so a relative import
      // "./vendor/xterm.mjs" resolves to <outDir>/assets/vendor/xterm.mjs.
      const outDir = options.dir ?? "dist";
      const vendorDir = path.join(outDir, "assets", "vendor");
      fs.mkdirSync(vendorDir, { recursive: true });

      const src = path.resolve(root, "node_modules/@xterm/xterm/lib/xterm.mjs");
      const dest = path.join(vendorDir, "xterm.mjs");
      fs.copyFileSync(src, dest);
    },
  };
}

/** Plugins shared by the web and Electron-renderer builds. */
export const sharedPlugins = (root: string): Array<Plugin> => [
  externalizeXterm(root),
  react({
    plugins: [
      [
        "@swc/plugin-styled-components",
        {
          displayName: true,
          fileName: true,
          ssr: false,
        },
      ],
    ],
  }),
];

/** Module-path alias (`~` -> src) shared by both builds. */
export const sharedResolve = (root: string): { alias: Record<string, string> } => ({
  alias: {
    "~": path.resolve(root, "src"),
  },
});

/** SCSS load paths shared by both builds (lets modules `@use "scrollbar" as *;`). */
export const sharedCss = (root: string): import("vite").CSSOptions => ({
  preprocessorOptions: {
    scss: {
      // Vite 5 defaults to the legacy Sass API, which expects `includePaths`
      // (the modern API's equivalent is `loadPaths`).
      includePaths: [path.resolve(root, "src/styles")],
    },
  },
});

/**
 * Dependencies that are only discovered at runtime (transitively imported, or
 * previously only type-imported). Pre-bundling them keeps Vite dev mode from
 * re-optimizing mid-request and triggering a full reload — which breaks Electron
 * integration tests on CI. If you add a new *runtime* import of a package that
 * was previously only type-imported or consumed transitively, add it here.
 */
export const sharedOptimizeDeps: { include: Array<string> } = {
  include: ["marked", "@radix-ui/react-popover", "@tiptap/suggestion"],
};

/**
 * Telemetry + API-base `define`s. `apiUrlBaseExpr` and `sentryRelease` differ
 * per target, so each entry config supplies them:
 *   - web:      apiUrlBaseExpr = JSON.stringify(SCULPTOR_API_BASE_URL || "")
 *               (same-origin), sentryRelease falls back to the git sha.
 *   - renderer: apiUrlBaseExpr = "undefined" (the preload injects
 *               window.sculptor.backendPort), sentryRelease falls back to "".
 *
 * `apiUrlBaseExpr` is the raw substitution text (a Vite `define` value), not a
 * value to be JSON-encoded again.
 */
export const sharedDefine = (
  env: Record<string, string>,
  opts: { apiUrlBaseExpr: string; sentryRelease: string },
): Record<string, string> => ({
  FRONTEND_SENTRY_DSN: JSON.stringify(env.SCULPTOR_FRONTEND_SENTRY_DSN || ""),
  FRONTEND_SENTRY_RELEASE_ID: JSON.stringify(opts.sentryRelease),
  FRONTEND_POSTHOG_TOKEN: JSON.stringify(env.SCULPTOR_FRONTEND_POSTHOG_TOKEN || ""),
  FRONTEND_POSTHOG_HOST: JSON.stringify(env.SCULPTOR_FRONTEND_POSTHOG_HOST || "https://us.i.posthog.com"),
  API_URL_BASE: opts.apiUrlBaseExpr,
});
