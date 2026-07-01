// Web (and OpenHost) Vite build. Only the web-specific knobs live here — the
// dev/prod branch, proxy, env loading, and shared plugin pipeline come from
// `defineFrontendConfig` in vite.base.config.ts. Web specifics: a same-origin
// API_URL_BASE, a sentry release that falls back to the git sha, a
// build-start hook that regenerates the API types, and the PWA manifest +
// service worker (web-only: the Electron renderer must never register a
// service worker or advertise installability).
import { execSync } from "node:child_process";

import { VitePWA } from "vite-plugin-pwa";

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
        execSync("pnpm run generate-api", { stdio: "inherit" });
      },
    },
    // Makes the web UI installable as a PWA (home-screen icon, standalone
    // window). The service worker intentionally caches nothing of the app
    // (its precache holds only the webmanifest, which the plugin adds
    // unconditionally): the frontend is served by the backend it talks to,
    // so letting a service worker serve stale assets could skew the frontend
    // against its own backend. It exists only to satisfy installability
    // heuristics and as the future home for Web Push (SCU-1656). Every
    // launch loads the app from the server, exactly like a browser tab.
    ...VitePWA({
      registerType: "autoUpdate",
      // Inject a plain <script> into the built index.html rather than
      // importing a virtual module from app code, so the Electron renderer
      // build (which does not include this plugin) needs no changes.
      injectRegister: "script-defer",
      manifest: {
        name: "Sculptor",
        short_name: "Sculptor",
        description: "Sculptor by Imbue — parallel coding agents",
        id: "/",
        start_url: "/",
        scope: "/",
        display: "standalone",
        // Matches the icon background so the install splash is seamless. The
        // in-app appearance (light/dark) is a runtime user setting the static
        // manifest cannot follow.
        theme_color: "#f2f0e7",
        background_color: "#f2f0e7",
        icons: [
          { src: "/pwa-192x192.png", sizes: "192x192", type: "image/png" },
          { src: "/pwa-512x512.png", sizes: "512x512", type: "image/png" },
          {
            // Full-bleed with the glyph inside the central 80% safe zone, so
            // circular launcher masks (e.g. Pixel) don't clip it.
            src: "/pwa-maskable-512x512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable",
          },
        ],
      },
      // The plugin force-adds the manifest icons to the precache unless told
      // not to; keep the precache truly empty.
      includeManifestIcons: false,
      workbox: {
        // No precache and no offline navigation fallback — see the caching
        // rationale above. Do not add globPatterns here without solving
        // frontend/backend version skew first.
        globPatterns: [],
        navigateFallback: null,
        cleanupOutdatedCaches: true,
      },
    }),
  ],
});
