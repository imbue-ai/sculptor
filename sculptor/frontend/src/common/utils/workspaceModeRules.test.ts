import { describe, expect, it } from "vitest";

import { WorkspaceInitializationStrategy } from "~/api";

import { hasRequiredCreationFields, toCreateRequestFields } from "./workspaceModeRules.ts";

const { IN_PLACE, CLONE, WORKTREE } = WorkspaceInitializationStrategy;

describe("toCreateRequestFields", () => {
  it.each([
    { mode: IN_PLACE, expected: { branchName: undefined, sourceBranch: undefined } },
    { mode: CLONE, expected: { branchName: "dev/ws", sourceBranch: "main" } },
    { mode: WORKTREE, expected: { branchName: "dev/ws", sourceBranch: "main" } },
  ])("sends only the fields $mode uses, trimmed", ({ mode, expected }) => {
    expect(toCreateRequestFields({ mode, branchName: "  dev/ws ", sourceBranch: " main" })).toEqual(expected);
  });

  it.each([IN_PLACE, CLONE, WORKTREE])("leaves blank fields out for %s", (mode) => {
    expect(toCreateRequestFields({ mode, branchName: "   ", sourceBranch: "" })).toEqual({
      branchName: undefined,
      sourceBranch: undefined,
    });
  });
});

describe("hasRequiredCreationFields", () => {
  it.each([
    { mode: IN_PLACE, branchName: "", sourceBranch: undefined, expected: true },
    { mode: CLONE, branchName: "", sourceBranch: undefined, expected: true },
    { mode: CLONE, branchName: "dev/ws", sourceBranch: "main", expected: true },
    { mode: WORKTREE, branchName: "dev/ws", sourceBranch: "main", expected: true },
    { mode: WORKTREE, branchName: "  ", sourceBranch: "main", expected: false },
    { mode: WORKTREE, branchName: "dev/ws", sourceBranch: undefined, expected: false },
    { mode: WORKTREE, branchName: "dev/ws", sourceBranch: "", expected: false },
  ])(
    "is $expected for $mode with branch name '$branchName' and source branch '$sourceBranch'",
    ({ mode, branchName, sourceBranch, expected }) => {
      expect(hasRequiredCreationFields({ mode, branchName, sourceBranch })).toBe(expected);
    },
  );
});
