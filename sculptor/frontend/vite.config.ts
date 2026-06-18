// TODO (PROD-2161): `vite.renderer.config.ts` should inherit from this config so that both our web and electron builds are close to equivalent
import react from "@vitejs/plugin-react-swc";
import { execSync } from "child_process";
import fs from "node:fs";
import path from "node:path";
import { defineConfig, loadEnv, type UserConfig } from "vite";

import { pluginRuntimeStubs } from "./vite-plugins/plugin-runtime-stubs.ts";

// This is just a backup function to use in case SCULPTOR_SENTRY_RELEASE_ID is not set.
const getGitSha = (): string => {
  try {
    return execSync("git rev-parse --short HEAD", { encoding: "utf8" }).trim();
  } catch {
    return "unknown";
  }
};

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
function externalizeXterm(): import("vite").Plugin {
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

      const src = path.resolve(__dirname, "node_modules/@xterm/xterm/lib/xterm.mjs");
      const dest = path.join(vendorDir, "xterm.mjs");
      fs.copyFileSync(src, dest);
    },
  };
}

const ENABLED_PLUGINS = [
  externalizeXterm(),
  pluginRuntimeStubs(),
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
  {
    name: "generate-types",
    buildStart(): void {
      console.log("Generating dynamic types...");
      execSync("npm run generate-api", { stdio: "inherit" });
    },
  },
];

// For more info: https://github.com/vitejs/vite-plugin-react-swc
/* eslint-disable-next-line import/no-default-export */
export default defineConfig(({ command, mode }): UserConfig => {
  const env = loadEnv(mode, process.cwd(), "");

  const sentryDsn = env.SCULPTOR_FRONTEND_SENTRY_DSN || "";
  const sentryRelease = env.SCULPTOR_SENTRY_RELEASE_ID || `${getGitSha()}`;
  const posthogToken = env.SCULPTOR_FRONTEND_POSTHOG_TOKEN || "";
  const posthogHost = env.SCULPTOR_FRONTEND_POSTHOG_HOST || "https://us.i.posthog.com";

  const apiBaseUrl: string = env.SCULPTOR_API_BASE_URL || "";

  const baseConfig: UserConfig = {
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
      API_URL_BASE: JSON.stringify(apiBaseUrl),
    },
    build: {
      sourcemap: true,
    },
    clearScreen: false,
    server: {
      port: 5174,
      strictPort: true,
      host: "127.0.0.1",
    },
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

  console.log(`Started vite with command: "${command}" and mode: "${mode}"`);
  console.log(`Sentry DSN: ${sentryDsn}`);
  console.log(`Sentry Release: ${sentryRelease}`);

  if (command === "serve" || mode === "development") {
    const apiPort = Number(env.SCULPTOR_API_PORT || 5050);
    const fePort = Number(env.SCULPTOR_FRONTEND_PORT || 5174);
    const apiTarget = env.SCULPTOR_CUSTOM_BACKEND_URL || `http://127.0.0.1:${apiPort}`;

    console.log(`Proxying frontend: target=${apiTarget} SCULPTOR_FRONTEND_PORT=${fePort}`);

    return {
      ...baseConfig,
      // this configures the proxy server when running in development mode
      server: {
        port: fePort,
        strictPort: true,
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
      },
    };
  }
  return baseConfig;
});
