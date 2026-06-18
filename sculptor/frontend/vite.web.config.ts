// Web (and OpenHost) Vite build. Only the web-specific knobs live here — the
// dev/prod branch, proxy, env loading, and shared plugin pipeline come from
// `defineFrontendConfig` in vite.base.config.ts. Web specifics: a same-origin
// API_URL_BASE, a sentry release that falls back to the git sha, and a
// build-start hook that regenerates the API types.
import { execSync } from "node:child_process";

import { defineFrontendConfig } from "./vite.base.config.ts";

// Backup for SCULPTOR_SENTRY_RELEASE_ID when it isn't set.
const getGitSha = (): string => {
  try {
    return execSync("git rev-parse --short HEAD", { encoding: "utf8" }).trim();
  } catch {
    return "unknown";
  }
};

/* eslint-disable-next-line import/no-default-export */
export default defineFrontendConfig({
  root: __dirname,
  defaultFrontendPort: 5174,
  apiUrlBase: (env): string => JSON.stringify(env.SCULPTOR_API_BASE_URL || ""),
  sentryRelease: (env): string => env.SCULPTOR_SENTRY_RELEASE_ID || getGitSha(),
  extraPlugins: [
    {
      name: "generate-types",
      buildStart(): void {
        console.log("Generating dynamic types...");
        execSync("npm run generate-api", { stdio: "inherit" });
      },
    },
  ],
});
