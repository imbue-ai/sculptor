// Web (and OpenHost) Vite build. Shares its plugin pipeline with the Electron
// renderer via vite.base.config.ts; only the web-specific knobs live here:
// base "/" (absolute asset paths), outDir dist (Vite default), and a
// same-origin API_URL_BASE.
import { execSync } from "node:child_process";

import { defineConfig, loadEnv, type UserConfig } from "vite";

import { sharedCss, sharedDefine, sharedOptimizeDeps, sharedPlugins, sharedResolve } from "./vite.base.config.ts";

const root = __dirname;

// Backup for SCULPTOR_SENTRY_RELEASE_ID when it isn't set.
const getGitSha = (): string => {
  try {
    return execSync("git rev-parse --short HEAD", { encoding: "utf8" }).trim();
  } catch {
    return "unknown";
  }
};

/* eslint-disable-next-line import/no-default-export */
export default defineConfig(({ command, mode }): UserConfig => {
  const env = loadEnv(mode, process.cwd(), "");

  const sentryRelease = env.SCULPTOR_SENTRY_RELEASE_ID || getGitSha();
  const apiBaseUrl: string = env.SCULPTOR_API_BASE_URL || "";

  const baseConfig: UserConfig = {
    // The backend serves the bundled UI from the site root, so asset URLs must
    // be absolute — a relative base would break nested-route hard refreshes.
    base: "/",
    optimizeDeps: sharedOptimizeDeps,
    define: sharedDefine(env, { apiUrlBaseExpr: JSON.stringify(apiBaseUrl), sentryRelease }),
    build: {
      sourcemap: true,
    },
    clearScreen: false,
    server: {
      port: 5174,
      strictPort: true,
      host: "127.0.0.1",
    },
    plugins: [
      ...sharedPlugins(root),
      {
        name: "generate-types",
        buildStart(): void {
          console.log("Generating dynamic types...");
          execSync("npm run generate-api", { stdio: "inherit" });
        },
      },
    ],
    envPrefix: "SCULPTOR_",
    resolve: sharedResolve(root),
    css: sharedCss(root),
  };

  console.log(`Started vite with command: "${command}" and mode: "${mode}"`);

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
