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
    },
  },
  test: {
    environment: "jsdom",
    globals: false,
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: { modules: { classNameStrategy: "non-scoped" } },
  },
});
