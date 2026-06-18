// Electron renderer Vite build. Only the renderer-specific knobs live here — the
// dev/prod branch, proxy, env loading, and shared plugin pipeline come from
// `defineFrontendConfig` in vite.base.config.ts. Renderer specifics: API_URL_BASE
// undefined so the renderer falls back to the port the preload injects
// (window.sculptor.backendPort), outDir .vite/build/renderer (electron-forge owns
// that path), and HMR gated under pytest so integration tests don't hit reload
// races.
import path from "node:path";
import { fileURLToPath } from "node:url";

import { defineFrontendConfig } from "./vite.base.config.ts";

const root = path.dirname(fileURLToPath(import.meta.url));

/* eslint-disable-next-line import/no-default-export */
export default defineFrontendConfig({
  root,
  defaultFrontendPort: 5173,
  // Undefined so the renderer uses the backend port the preload injects into
  // window.sculptor.backendPort instead of a baked-in base URL.
  apiUrlBase: (): string => "undefined",
  sentryRelease: (env): string => env.SCULPTOR_SENTRY_RELEASE_ID || "",
  gateHmrUnderPytest: true,
  build: {
    // electron-forge bundles everything under .vite/build.
    outDir: ".vite/build/renderer",
    emptyOutDir: true,
    rollupOptions: {
      input: { main: path.resolve(root, "index.html") },
    },
  },
});
