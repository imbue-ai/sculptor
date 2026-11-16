import { describe, expect, it } from "vitest";

import { WorkspaceInitializationStrategy } from "~/api";

import {
  defaultSourceFor,
  hasRequiredCreationFields,
  offeredCreationModes,
  repositoryWorkspaceVcs,
  resolveCreationMode,
  toCreateRequestFields,
  WORKSPACE_MODE_RULES,
} from "./workspaceModeRules.ts";

const { IN_PLACE, CLONE, WORKTREE, JJ_WORKSPACE } = WorkspaceInitializationStrategy;

describe("toCreateRequestFields", () => {
  it.each([
    { mode: IN_PLACE, expected: { branchName: undefined, sourceBranch: undefined } },
    { mode: CLONE, expected: { branchName: "dev/ws", sourceBranch: "main" } },
    { mode: WORKTREE, expected: { branchName: "dev/ws", sourceBranch: "main" } },
    { mode: JJ_WORKSPACE, expected: { branchName: "dev/ws", sourceBranch: "main" } },
  ])("sends only the fields $mode uses, trimmed", ({ mode, expected }) => {
    expect(toCreateRequestFields({ mode, branchName: "  dev/ws ", sourceBranch: " main" })).toEqual(expected);
  });

  it.each(Object.values(WorkspaceInitializationStrategy))("leaves blank fields out for %s", (mode) => {
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
    { mode: JJ_WORKSPACE, branchName: "dev/ws", sourceBranch: undefined, expected: true },
    { mode: JJ_WORKSPACE, branchName: "dev/ws", sourceBranch: "main", expected: true },
    { mode: JJ_WORKSPACE, branchName: "  ", sourceBranch: "main", expected: false },
  ])(
    "is $expected for $mode with branch name '$branchName' and source branch '$sourceBranch'",
    ({ mode, branchName, sourceBranch, expected }) => {
      expect(hasRequiredCreationFields({ mode, branchName, sourceBranch })).toBe(expected);
    },
  );
});

describe("WORKSPACE_MODE_RULES", () => {
  it.each([
    { mode: IN_PLACE, noun: "branch" },
    { mode: CLONE, noun: "branch" },
    { mode: WORKTREE, noun: "branch" },
    { mode: JJ_WORKSPACE, noun: "bookmark" },
  ])("names what $mode creates a $noun", ({ mode, noun }) => {
    expect(WORKSPACE_MODE_RULES[mode].nameNoun).toBe(noun);
  });

  it("explains an unused source in the words of the mode that leaves it out", () => {
    expect(WORKSPACE_MODE_RULES[IN_PLACE].sourceBranch).toEqual({
      rule: "unused",
      whyUnused: "In-place workspaces use the current branch in your repository",
    });
  });
});

describe("defaultSourceFor", () => {
  it.each([
    { mode: IN_PLACE, expected: "main" },
    { mode: CLONE, expected: "main" },
    { mode: WORKTREE, expected: "main" },
    // A jj workspace with no source picked starts from its target, which the backend resolves.
    { mode: JJ_WORKSPACE, expected: undefined },
  ])("is $expected for $mode in a repository on main", ({ mode, expected }) => {
    expect(defaultSourceFor({ mode, currentBranch: "main" })).toBe(expected);
  });
});

describe("repositoryWorkspaceVcs", () => {
  it.each([
    { createsJjWorkspaces: true, usesJjForNewWorkspaces: true, isJjAvailable: true, expected: "jj" },
    // creates_jj_workspaces folds in jj's availability, so the flag tells a jj repository whose jj is gone.
    { createsJjWorkspaces: false, usesJjForNewWorkspaces: true, isJjAvailable: false, expected: "jj-unavailable" },
    { createsJjWorkspaces: false, usesJjForNewWorkspaces: false, isJjAvailable: false, expected: "git" },
    { createsJjWorkspaces: false, usesJjForNewWorkspaces: false, isJjAvailable: true, expected: "git" },
    // The repository state has not arrived, or the colocation is gone and the backend is clearing the flag.
    { createsJjWorkspaces: false, usesJjForNewWorkspaces: true, isJjAvailable: true, expected: "git" },
  ])(
    "is $expected when it creates jj workspaces: $createsJjWorkspaces, its flag is $usesJjForNewWorkspaces and jj is available: $isJjAvailable",
    ({ expected, ...facts }) => {
      expect(repositoryWorkspaceVcs(facts)).toBe(expected);
    },
  );
});

describe("resolveCreationMode", () => {
  it.each([
    { remembered: undefined, vcs: "git", expected: WORKTREE },
    { remembered: undefined, vcs: "jj", expected: JJ_WORKSPACE },
    { remembered: undefined, vcs: "jj-unavailable", expected: JJ_WORKSPACE },
    // jj takes Worktree's place in a repository that creates jj workspaces, and gives it back when it stops.
    { remembered: WORKTREE, vcs: "jj", expected: JJ_WORKSPACE },
    { remembered: JJ_WORKSPACE, vcs: "git", expected: WORKTREE },
    { remembered: JJ_WORKSPACE, vcs: "jj-unavailable", expected: JJ_WORKSPACE },
    // Clone and in-place stay git whatever the repository's jj setting.
    { remembered: CLONE, vcs: "jj", expected: CLONE },
    { remembered: IN_PLACE, vcs: "jj", expected: IN_PLACE },
    { remembered: CLONE, vcs: "git", expected: CLONE },
  ] as const)("picks $expected for $remembered in a $vcs repository", ({ remembered, vcs, expected }) => {
    expect(resolveCreationMode({ remembered, vcs })).toBe(expected);
  });
});

describe("offeredCreationModes", () => {
  it.each([
    { isolatedMode: WORKTREE, isCloneEnabled: false, isInPlaceEnabled: false, value: WORKTREE, expected: [WORKTREE] },
    {
      isolatedMode: JJ_WORKSPACE,
      isCloneEnabled: false,
      isInPlaceEnabled: false,
      value: JJ_WORKSPACE,
      expected: [JJ_WORKSPACE],
    },
    // jj takes Worktree's place; clone and in-place stay under their flags.
    {
      isolatedMode: JJ_WORKSPACE,
      isCloneEnabled: true,
      isInPlaceEnabled: true,
      value: JJ_WORKSPACE,
      expected: [JJ_WORKSPACE, CLONE, IN_PLACE],
    },
    // A mode whose flag is off stays offered while it is the value, so the user can leave it.
    {
      isolatedMode: JJ_WORKSPACE,
      isCloneEnabled: false,
      isInPlaceEnabled: false,
      value: CLONE,
      expected: [JJ_WORKSPACE, CLONE],
    },
  ] as const)(
    "offers $expected with $isolatedMode, clone on: $isCloneEnabled, in-place on: $isInPlaceEnabled, on $value",
    ({ expected, ...inputs }) => {
      expect(offeredCreationModes(inputs)).toEqual(expected);
    },
  );
});
