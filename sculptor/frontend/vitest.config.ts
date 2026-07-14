import path from "node:path";

import { defineConfig } from "vitest/config";

import { extensionRuntimeStubs } from "./vite-plugins/extension-runtime-stubs.ts";

/* eslint-disable-next-line import/no-default-export */
export default defineConfig({
  // The host-versions virtual module is imported by hostRuntime.ts, which the
  // extension manager pulls in under test; register the plugin so it resolves.
  plugins: [extensionRuntimeStubs()],
  resolve: {
    alias: {
      "~": path.resolve(__dirname, "src"),
      // Resolve the bare SDK specifier to host source, mirroring the bundled
      // extensions' tsconfig path, so extension tests can import `@sculptor/extension-sdk`.
      "@sculptor/extension-sdk": path.resolve(__dirname, "src/extensions/sdk/index.ts"),
    },
  },
  test: {
    environment: "jsdom",
    globals: false,
    setupFiles: ["./vitest.setup.ts"],
    // `extensions/**` covers the bundled extensions' own unit tests (e.g. linear-issue);
    // they import only extension-local modules plus the aliased SDK above.
    include: ["src/**/*.test.{ts,tsx}", "extensions/**/*.test.{ts,tsx}"],
    css: { modules: { classNameStrategy: "non-scoped" } },
  },
});
