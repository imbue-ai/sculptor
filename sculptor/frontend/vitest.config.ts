import path from "node:path";

import { defineConfig } from "vitest/config";

import { pluginRuntimeStubs } from "./vite-plugins/plugin-runtime-stubs.ts";

/* eslint-disable-next-line import/no-default-export */
export default defineConfig({
  // The host-versions virtual module is imported by hostRuntime.ts, which the
  // plugin manager pulls in under test; register the plugin so it resolves.
  plugins: [pluginRuntimeStubs()],
  resolve: {
    alias: {
      "~": path.resolve(__dirname, "src"),
      // Resolve the bare SDK specifier to host source, mirroring the bundled
      // plugins' tsconfig path, so plugin tests can import `@sculptor/plugin-sdk`.
      "@sculptor/plugin-sdk": path.resolve(__dirname, "src/plugins/sdk/index.ts"),
    },
  },
  test: {
    environment: "jsdom",
    globals: false,
    setupFiles: ["./vitest.setup.ts"],
    // `plugins/**` covers the bundled plugins' own unit tests (e.g. linear-issue);
    // they import only plugin-local modules plus the aliased SDK above.
    include: ["src/**/*.test.{ts,tsx}", "plugins/**/*.test.{ts,tsx}"],
    css: { modules: { classNameStrategy: "non-scoped" } },
  },
});
