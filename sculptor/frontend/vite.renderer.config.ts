// Electron renderer Vite build. Shares its plugin pipeline with the web build
// via vite.base.config.ts; only the renderer-specific knobs live here:
// base "/" (absolute paths; the packaged renderer is served from the
// sculptor://app origin, not file://), outDir .vite/build/renderer
// (electron-forge owns that path), and API_URL_BASE undefined so the renderer
// falls back to the port the preload injects (window.sculptor.backendPort).
import path from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig, loadEnv, type UserConfig } from "vite";

import { sharedCss, sharedDefine, sharedOptimizeDeps, sharedPlugins, sharedResolve } from "./vite.base.config.ts";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const root = __dirname;
const inputHtml = path.resolve(__dirname, "index.html");

/* eslint-disable-next-line import/no-default-export */
export default defineConfig(({ command, mode }): UserConfig => {
  const env = loadEnv(mode, process.cwd(), "");

  const sentryRelease = env.SCULPTOR_SENTRY_RELEASE_ID || "";

  const baseConfig: UserConfig = {
    root,
    optimizeDeps: sharedOptimizeDeps,
    define: sharedDefine(env, {
      // Undefined so the renderer uses the backend port the preload injects into
      // window.sculptor.backendPort instead of a baked-in base URL.
      apiUrlBaseExpr: "undefined",
      sentryRelease,
    }),
    build: {
      sourcemap: true,
      // By default, forge will bundle everything in `.vite/build`.
      outDir: ".vite/build/renderer",
      emptyOutDir: true,
      rollupOptions: {
        input: { main: inputHtml },
      },
    },
    clearScreen: false,
    // Use an absolute asset base so the built index.html references
    // `/assets/...`. The packaged renderer is served from the real
    // `sculptor://app` origin (and the Vite dev server in development), not
    // `file://`, so absolute paths resolve against the origin root regardless
    // of the document's path — the app-scheme handler serves `/assets/...`
    // directly. A relative base (`./`) instead resolves assets against the
    // document directory, which breaks if the document path ever gains a
    // trailing segment (e.g. `index.html/`).
    base: "/",
    plugins: sharedPlugins(root),
    envPrefix: "SCULPTOR_",
    resolve: sharedResolve(root),
    css: sharedCss(root),
  };

  if (command === "serve" || mode === "development") {
    const apiPort = Number(env.SCULPTOR_API_PORT || 5050);
    const fePort = Number(env.SCULPTOR_FRONTEND_PORT || 5173);
    const apiTarget = env.SCULPTOR_CUSTOM_BACKEND_URL || `http://127.0.0.1:${apiPort}`;

    console.log(`Proxying renderer: target=${apiTarget} SCULPTOR_FRONTEND_PORT=${fePort}`);

    return {
      ...baseConfig,
      // this configures the proxy server when running in development mode
      server: {
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
        },
        // HMR can cause race conditions in integration tests, so disable it.
        hmr: !env.PYTEST_CURRENT_TEST,
      },
    };
  }
  return baseConfig;
});
