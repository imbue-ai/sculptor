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
    // turns and the dependency-probe tests time out. Cap the concurrent file
    // count to leave CPU headroom, and give subprocess-bound tests a generous
    // per-test timeout (the default 5s is too tight for a probe under load).
    maxWorkers: "35%",
    testTimeout: 30000,
  },
});
