import path from "node:path";

import { defineConfig } from "vitest/config";

/* eslint-disable-next-line import/no-default-export */
export default defineConfig({
  resolve: {
    alias: {
      "~": path.resolve(__dirname, "src"),
    },
  },
  test: {
    environment: "node",
    globals: false,
    include: ["src/**/*.test.ts"],
  },
});
