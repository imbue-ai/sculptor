import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react-swc";
import type { BuildOptions, Plugin } from "vite";
import { defineConfig, loadEnv, type UserConfig } from "vite";

import { pluginRuntimeStubs } from "./vite-plugins/plugin-runtime-stubs.ts";

/**
 * Exclude ``@xterm/xterm`` from the bundle and serve it as a standalone
 * ES module.  See the detailed comment in vite.config.ts for the full
 * explanation.
 */
function externalizeXterm(): Plugin {
  return {
    name: "externalize-xterm",
    config(): { build: BuildOptions } {
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

      const src = path.resolve(__dirname, "node_modules/@xterm/xterm/lib/xterm.mjs");
      const dest = path.join(vendorDir, "xterm.mjs");
      fs.copyFileSync(src, dest);
    },
  };
}

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const root = __dirname;
const inputHtml = path.resolve(__dirname, "index.html");

/* eslint-disable-next-line import/no-default-export */
export default defineConfig(({ command, mode }): UserConfig => {
  const env = loadEnv(mode, process.cwd(), "");

  const sentryDsn = env.SCULPTOR_FRONTEND_SENTRY_DSN || "";
  const sentryRelease = env.SCULPTOR_SENTRY_RELEASE_ID || "";
  const posthogToken = env.SCULPTOR_FRONTEND_POSTHOG_TOKEN || "";
  const posthogHost = env.SCULPTOR_FRONTEND_POSTHOG_HOST || "https://us.i.posthog.com";

  console.log(`Started vite renderer with command: "${command}" and mode: "${mode}"`);
  console.log(`Sentry DSN: ${sentryDsn}`);
  console.log(`Sentry Release: ${sentryRelease}`);
  console.log(`PostHog token: ${posthogToken ? "set" : "(empty — telemetry disabled)"}`);
  console.log(`PostHog host: ${posthogHost}`);

  const ENABLED_PLUGINS = [externalizeXterm(), pluginRuntimeStubs(), react()];

  const baseConfig: UserConfig = {
    root,
    // Pre-bundle dependencies that are only discovered at runtime (e.g.,
    // transitively imported by other packages or previously only type-imported).
    // Without this, Vite dev mode discovers them mid-request, re-optimizes,
    // and triggers a full page reload — which breaks Electron integration
    // tests on CI. If you add a new *runtime* import of a package that was
    // previously only type-imported or consumed as a transitive dependency,
    // add it here.
    optimizeDeps: {
      include: ["marked", "@radix-ui/react-popover", "@tiptap/suggestion"],
    },
    define: {
      FRONTEND_SENTRY_DSN: JSON.stringify(sentryDsn),
      FRONTEND_SENTRY_RELEASE_ID: JSON.stringify(sentryRelease),
      FRONTEND_POSTHOG_TOKEN: JSON.stringify(posthogToken),
      FRONTEND_POSTHOG_HOST: JSON.stringify(posthogHost),
      // When serving with Electron,
      // preload.ts injects the backend port into the window.sculptor.backendPort,
      // and we leave this undefined so that the frontend will use that instead.
      API_URL_BASE: "undefined",
    },
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
    // Makes asset paths relative so it works even if you load via file:// later
    base: "./",
    plugins: ENABLED_PLUGINS,
    envPrefix: "SCULPTOR_",
    resolve: {
      alias: {
        "~": path.resolve(__dirname, "src"),
      },
    },
    css: {
      preprocessorOptions: {
        scss: {
          // Lets SCSS modules `@use "scrollbar" as *;` without relative paths.
          // Vite 5 defaults to the legacy Sass API, which expects
          // `includePaths` (the modern API's equivalent is `loadPaths`).
          includePaths: [path.resolve(__dirname, "src/styles")],
        },
      },
    },
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
