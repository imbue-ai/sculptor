import { describe, expect, it } from "vitest";

import { buildCommitMessage, buildCreatePrMessage } from "./agentPrompts.ts";

const PR_PROMPT =
  "Push my changes to origin and create a pull request using the GitHub CLI (gh). Write a clear description summarizing the changes.";
const COMMIT_PROMPT =
  "Stage every changed and untracked file, then commit with a comprehensive commit message. Do not leave any files unstaged.";

describe("buildCreatePrMessage", () => {
  it("appends the target branch to the prompt", () => {
    expect(buildCreatePrMessage({ prompt: PR_PROMPT, targetBranch: "origin/main" })).toBe(
      "Push my changes to origin and create a pull request using the GitHub CLI (gh). Write a clear description summarizing the changes.\n\nTarget the pull request against `origin/main`.",
    );
  });

  it("keeps every segment of a nested target branch", () => {
    expect(buildCreatePrMessage({ prompt: "Open a pull request", targetBranch: "feature/login" })).toBe(
      "Open a pull request\n\nTarget the pull request against `feature/login`.",
    );
  });

  it("sends the prompt alone when the workspace has no target branch", () => {
    expect(buildCreatePrMessage({ prompt: PR_PROMPT, targetBranch: null })).toBe(PR_PROMPT);
  });

  it("treats an empty target branch as no target", () => {
    expect(buildCreatePrMessage({ prompt: PR_PROMPT, targetBranch: "" })).toBe(PR_PROMPT);
  });
});

describe("buildCommitMessage", () => {
  it("sends the commit prompt as it is", () => {
    expect(buildCommitMessage({ prompt: COMMIT_PROMPT })).toBe(COMMIT_PROMPT);
  });
});
