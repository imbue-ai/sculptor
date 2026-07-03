// Shared Vite configuration for both frontend builds. `defineFrontendConfig`
// (at the bottom) builds the entire config — the dev/prod branch, the proxy,
// env loading, and the plugin pipeline — so each entry config only declares the
// handful of knobs that genuinely differ:
//
//   - vite.web.config.ts      (web / OpenHost):  API_URL_BASE "" (same-origin),
//                                                 sentry release from the git sha,
//                                                 a type-generation plugin
//   - vite.electron.config.ts (Electron renderer): API_URL_BASE undefined
//                                                 (preload injects the port),
//                                                 outDir .vite/build/renderer,
//                                                 HMR gated under pytest
//
// Each entry config passes its own `root` (the frontend dir) so path resolution
// here never depends on how Vite bundles this module.
import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

import react from "@vitejs/plugin-react-swc";
import {
  defineConfig,
  loadEnv,
  type HtmlTagDescriptor,
  type Plugin,
  type UserConfig,
  type UserConfigExport,
} from "vite";

import { bundledPlugins } from "./vite-plugins/bundled-plugins.ts";
import { pluginRuntimeStubs } from "./vite-plugins/plugin-runtime-stubs.ts";

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
  pluginRuntimeStubs(),
  bundledPlugins(),
  react(),
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
      // Vite 6 uses the modern Sass API, whose load-path option is `loadPaths`
      // (the legacy API's equivalent was `includePaths`).
      loadPaths: [path.resolve(root, "src/styles")],
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

/**
 * Target-specific knobs for {@link defineFrontendConfig}. Everything else — the
 * dev/prod branch, the proxy, env loading, and the shared
 * plugins/resolve/css/define — is identical across builds and lives in the
 * factory, so each entry config only declares what actually differs.
 */
export interface FrontendConfigOptions {
  /** Frontend dir; drives `root`, the `~` alias, SCSS load paths, and plugin file copies. */
  root: string;
  /** Dev-server port used when SCULPTOR_FRONTEND_PORT is unset (5174 web, 5173 renderer). */
  defaultFrontendPort: number;
  /** Raw `API_URL_BASE` define expression, derived from the loaded env. */
  apiUrlBase: (env: Record<string, string>) => string;
  /** Sentry release id (with its per-target fallback), derived from the loaded env. */
  sentryRelease: (env: Record<string, string>) => string;
  /**
   * Asset base. Defaults to "/" (absolute): both builds are served from an
   * origin root — the backend for web, the `sculptor://app` scheme (and the
   * Vite dev server in development) for the packaged renderer — never `file://`,
   * so assets resolve against the origin regardless of the document's path.
   * (Under the OpenHost preview front — SCULPTOR_OPENHOST_PROXY set — the factory
   * overrides this with `/proxy/<frontend-port>/`; see defineFrontendConfig.)
   */
  base?: string;
  /** Extra `build` options merged over the shared `{ sourcemap: true }`. */
  build?: import("vite").BuildOptions;
  /** Plugins appended after the shared pipeline (e.g. web's type generation). */
  extraPlugins?: Array<Plugin>;
  /** Disable HMR under pytest so integration tests don't hit reload races. */
  gateHmrUnderPytest?: boolean;
}

/**
 * OpenHost preview identity: inject `<meta name="sculptor-preview">` into
 * index.html so the /proxy/ switchboard (openhost-preview-fallback.html) and
 * the openhost-preview-switcher plugin can label this preview. A dev server has
 * no "build time" to report; instead branch/sha/dirty are read fresh from the
 * working tree on each index.html request. HMR patches modules without
 * refetching index.html, so a loaded page keeps the identity it loaded with —
 * but scanners always GET index.html anew, so listings stay current.
 *
 * Deliberately calls git per request rather than reusing an existing config
 * value: Vite carries no VCS context of its own, and the one git-derived value
 * we do have (the web build's sentry release sha, read once in
 * vite.web.config.ts) is frozen at config load. A preview session is
 * long-lived — commits land mid-session while HMR keeps serving — so a
 * boot-time identity would go stale exactly when the label matters. The cost
 * is a few ~10ms subprocess calls per index.html request, dev-only and gated
 * behind SCULPTOR_OPENHOST_PROXY.
 */
function previewIdentity(root: string): Plugin {
  const git = (args: string): string => {
    try {
      return execSync(`git ${args}`, { cwd: root, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
    } catch {
      return ""; // e.g. /app previews: the deploy image ships without .git
    }
  };
  return {
    name: "sculptor:preview-identity",
    transformIndexHtml(): Array<HtmlTagDescriptor> {
      const branch = git("branch --show-current");
      const sha = git("rev-parse --short HEAD");
      const dirty = git("status --porcelain") === "" ? "" : "*";
      // Without git (no branch AND no sha), fall back to the serving dir —
      // still enough to tell /app from a workspace checkout.
      const content = branch === "" && sha === "" ? root : `${branch}@${sha}${dirty}`;
      return [{ tag: "meta", attrs: { name: "sculptor-preview", content }, injectTo: "head" }];
    },
  };
}

/** Dev-only proxy server forwarding `/api`, `/ws`, and `/plugins/local` to the backend. */
function devServer(env: Record<string, string>, fePort: number): import("vite").ServerOptions {
  const apiPort = Number(env.SCULPTOR_API_PORT || 5050);
  const apiTarget = env.SCULPTOR_CUSTOM_BACKEND_URL || `http://127.0.0.1:${apiPort}`;

  console.log(`Proxying frontend: target=${apiTarget} SCULPTOR_FRONTEND_PORT=${fePort}`);

  return {
    port: fePort,
    strictPort: true,
    host: "127.0.0.1",
    proxy: {
      "/api": {
        target: apiTarget,
        changeOrigin: true,
        ws: true,
      },
      "/ws": {
        target: apiTarget,
        ws: true,
        rewriteWsOrigin: true,
      },
      // Local/dev plugins are served by the backend's `/plugins/local` static
      // mount; in production the backend serves the SPA too (same origin), but in
      // dev the SPA is on Vite, so forward this prefix to the backend or the
      // plugin loader's manifest fetch hits Vite's SPA fallback (HTML, not JSON).
      // Only `/plugins/local` — builtin plugins (`/plugins/<id>`) are Vite public
      // assets and must keep being served by Vite.
      "/plugins/local": {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  };
}

/**
 * Build the full Vite config for a frontend target from its {@link
 * FrontendConfigOptions}. Owns the dev/prod branch and the proxy so the entry
 * configs only declare what genuinely differs between web and the renderer.
 */
export function defineFrontendConfig(opts: FrontendConfigOptions): UserConfigExport {
  return defineConfig(({ command, mode }): UserConfig => {
    const env = loadEnv(mode, process.cwd(), "");

    console.log(`Started vite with command: "${command}" and mode: "${mode}"`);

    // OpenHost-only: behind the nginx /proxy/<port>/ front, the asset `base` and the
    // HMR client must both point at that sub-path. Derive base from the SAME frontend
    // port the dev server binds (see devServer below) so the two can never drift;
    // gated on SCULPTOR_OPENHOST_PROXY so normal dev/build is unaffected. (base can't
    // ride a `vite --base=…` CLI flag here: `pnpm run dev -- --base=…` forwards a stray
    // `--` that Vite treats as an end-of-options marker, silently dropping the flag.)
    const fePort = Number(env.SCULPTOR_FRONTEND_PORT || opts.defaultFrontendPort);
    const openhostProxyBase = env.SCULPTOR_OPENHOST_PROXY ? `/proxy/${fePort}/` : undefined;

    const config: UserConfig = {
      root: opts.root,
      base: openhostProxyBase ?? opts.base ?? "/",
      optimizeDeps: sharedOptimizeDeps,
      define: sharedDefine(env, {
        apiUrlBaseExpr: opts.apiUrlBase(env),
        sentryRelease: opts.sentryRelease(env),
      }),
      build: { sourcemap: true, ...opts.build },
      clearScreen: false,
      envPrefix: "SCULPTOR_",
      resolve: sharedResolve(opts.root),
      css: sharedCss(opts.root),
      plugins: [
        ...sharedPlugins(opts.root),
        ...(opts.extraPlugins ?? []),
        ...(openhostProxyBase ? [previewIdentity(opts.root)] : []),
      ],
    };

    if (command === "serve" || mode === "development") {
      const server = devServer(env, fePort);
      // OpenHost-only: when served behind the nginx /proxy/<port>/ front, accept the
      // public Host (forwarded by nginx) and dial the HMR client back through the TLS
      // edge (:443, wss) at the sub-path. The matching asset `base` is derived above;
      // these HMR bits have no CLI/base equivalent and must live here. Gated on
      // SCULPTOR_OPENHOST_PROXY so normal dev/build is unaffected.
      if (env.SCULPTOR_OPENHOST_PROXY) {
        server.allowedHosts = true;
        server.hmr = { protocol: "wss", clientPort: 443 };
      }
      // HMR can race in integration tests, so disable it there — but only force
      // the disable, leaving any other HMR config (e.g. the OpenHost override
      // above) intact otherwise.
      if (opts.gateHmrUnderPytest && env.PYTEST_CURRENT_TEST) {
        server.hmr = false;
      }
      config.server = server;
    }

    return config;
  });
}
