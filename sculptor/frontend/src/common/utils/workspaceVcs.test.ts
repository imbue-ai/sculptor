import { describe, expect, it } from "vitest";

import { WorkspaceInitializationStrategy } from "~/api";

import { workspaceVcsOf } from "./workspaceVcs.ts";

describe("workspaceVcsOf", () => {
  it.each([
    { initializationStrategy: WorkspaceInitializationStrategy.IN_PLACE, expected: "git" },
    { initializationStrategy: WorkspaceInitializationStrategy.CLONE, expected: "git" },
    { initializationStrategy: WorkspaceInitializationStrategy.WORKTREE, expected: "git" },
    { initializationStrategy: WorkspaceInitializationStrategy.JJ_WORKSPACE, expected: "jj" },
  ])("is $expected for a $initializationStrategy workspace", ({ initializationStrategy, expected }) => {
    expect(workspaceVcsOf({ initializationStrategy })).toBe(expected);
  });
});
