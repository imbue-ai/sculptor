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
    // Many suites spawn real subprocesses (git worktrees, node-pty, the agent
    // harnesses against fake binaries). Running every file concurrently
    // saturates CPU and starves those subprocesses, so the harness end-to-end
    // turns time out. Cap the concurrent file count to leave headroom.
    maxWorkers: "50%",
    minWorkers: 1,
  },
});
