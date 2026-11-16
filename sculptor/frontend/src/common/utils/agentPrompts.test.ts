import { describe, expect, it } from "vitest";

import { buildCommitMessage, buildCreatePrMessage } from "./agentPrompts.ts";

const PR_PROMPT =
  "Push my changes to origin and create a pull request using the GitHub CLI (gh). Write a clear description summarizing the changes.";
const COMMIT_PROMPT =
  "Stage every changed and untracked file, then commit with a comprehensive commit message. Do not leave any files unstaged.";
const JJ_PREAMBLE = "This is a jj workspace with no git inside, so use jj rather than git.";

describe("buildCreatePrMessage", () => {
  describe("for a git workspace", () => {
    it("appends the target branch to the prompt", () => {
      expect(buildCreatePrMessage({ prompt: PR_PROMPT, workspace: { vcs: "git", targetBranch: "origin/main" } })).toBe(
        "Push my changes to origin and create a pull request using the GitHub CLI (gh). Write a clear description summarizing the changes.\n\nTarget the pull request against `origin/main`.",
      );
    });

    it("keeps every segment of a nested target branch", () => {
      expect(
        buildCreatePrMessage({
          prompt: "Open a pull request",
          workspace: { vcs: "git", targetBranch: "feature/login" },
        }),
      ).toBe("Open a pull request\n\nTarget the pull request against `feature/login`.");
    });

    it("sends the prompt alone when the workspace has no target branch", () => {
      expect(buildCreatePrMessage({ prompt: PR_PROMPT, workspace: { vcs: "git", targetBranch: null } })).toBe(
        PR_PROMPT,
      );
    });

    it("treats an empty target branch as no target", () => {
      expect(buildCreatePrMessage({ prompt: PR_PROMPT, workspace: { vcs: "git", targetBranch: "" } })).toBe(PR_PROMPT);
    });
  });

  describe("for a jj workspace", () => {
    it("pushes the bookmark and opens the pull request from it into the target's base", () => {
      expect(
        buildCreatePrMessage({
          prompt: "Open a pull request",
          workspace: {
            vcs: "jj",
            bookmark: { status: "set", name: "dev/login" },
            target: { bookmark: "main@origin", prBaseName: "main" },
          },
        }),
      ).toBe(
        `Open a pull request\n\n${JJ_PREAMBLE} Push the bookmark \`dev/login\` with \`jj git push -b dev/login\`, then open the pull request from \`dev/login\` into \`main\` with \`gh pr create --head dev/login --base main\`.`,
      );
    });

    it("asks for the requested bookmark first when the workspace has none", () => {
      expect(
        buildCreatePrMessage({
          prompt: "Open a pull request",
          workspace: {
            vcs: "jj",
            bookmark: { status: "missing", requestedName: "dev/login" },
            target: { bookmark: "main@origin", prBaseName: "main" },
          },
        }),
      ).toBe(
        `Open a pull request\n\n${JJ_PREAMBLE} First create the bookmark \`dev/login\` on your latest described change with \`jj bookmark create dev/login -r <change>\`. Push the bookmark \`dev/login\` with \`jj git push -b dev/login\`, then open the pull request from \`dev/login\` into \`main\` with \`gh pr create --head dev/login --base main\`.`,
      );
    });

    it("asks for a bookmark of the agent's naming when none was requested", () => {
      expect(
        buildCreatePrMessage({
          prompt: "Open a pull request",
          workspace: {
            vcs: "jj",
            bookmark: { status: "missing", requestedName: null },
            target: { bookmark: "main@origin", prBaseName: "main" },
          },
        }),
      ).toBe(
        `Open a pull request\n\n${JJ_PREAMBLE} First create a bookmark on your latest described change with \`jj bookmark create <name> -r <change>\`. Push the bookmark with \`jj git push -b <name>\`, then open the pull request from it into \`main\` with \`gh pr create --head <name> --base main\`.`,
      );
    });

    it("names the target bookmark when its pull request base is not known yet", () => {
      expect(
        buildCreatePrMessage({
          prompt: "Open a pull request",
          workspace: {
            vcs: "jj",
            bookmark: { status: "set", name: "dev/login" },
            target: { bookmark: "main@origin", prBaseName: null },
          },
        }),
      ).toBe(
        `Open a pull request\n\n${JJ_PREAMBLE} Push the bookmark \`dev/login\` with \`jj git push -b dev/login\`, then open the pull request from \`dev/login\` into the branch the target bookmark \`main@origin\` tracks.`,
      );
    });

    it("leaves the base to gh when the workspace has no target", () => {
      expect(
        buildCreatePrMessage({
          prompt: "Open a pull request",
          workspace: { vcs: "jj", bookmark: { status: "set", name: "dev/login" }, target: null },
        }),
      ).toBe(
        `Open a pull request\n\n${JJ_PREAMBLE} Push the bookmark \`dev/login\` with \`jj git push -b dev/login\`, then open the pull request from \`dev/login\` with \`gh pr create --head dev/login\`.`,
      );
    });
  });
});

describe("buildCommitMessage", () => {
  it("sends the commit prompt as it is for a git workspace", () => {
    expect(buildCommitMessage({ prompt: COMMIT_PROMPT, workspace: { vcs: "git" } })).toBe(COMMIT_PROMPT);
  });

  it("asks a jj workspace's agent to move its bookmark onto the committed change", () => {
    expect(
      buildCommitMessage({
        prompt: "Commit",
        workspace: { vcs: "jj", bookmark: { status: "set", name: "dev/login" } },
      }),
    ).toBe(
      `Commit\n\n${JJ_PREAMBLE} Then move the bookmark \`dev/login\` onto the change you committed: \`jj bookmark set dev/login -r @-\` after \`jj commit\`.`,
    );
  });

  it("asks a jj workspace's agent to create the requested bookmark when there is none", () => {
    expect(
      buildCommitMessage({
        prompt: "Commit",
        workspace: { vcs: "jj", bookmark: { status: "missing", requestedName: "dev/login" } },
      }),
    ).toBe(
      `Commit\n\n${JJ_PREAMBLE} Then create the bookmark \`dev/login\` on the change you committed: \`jj bookmark create dev/login -r @-\` after \`jj commit\`.`,
    );
  });

  it("asks for a bookmark of the agent's naming when none was requested", () => {
    expect(
      buildCommitMessage({
        prompt: "Commit",
        workspace: { vcs: "jj", bookmark: { status: "missing", requestedName: null } },
      }),
    ).toBe(
      `Commit\n\n${JJ_PREAMBLE} Then create a bookmark on the change you committed: \`jj bookmark create <name> -r @-\` after \`jj commit\`.`,
    );
  });
});
