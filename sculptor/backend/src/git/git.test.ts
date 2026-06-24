import { mkdtempSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { runProcessToCompletion } from "~/environment/process";
import {
  branchExists,
  currentBranch,
  previewBranchName,
  resolvePattern,
  revParseHead,
  setupWorkspace,
  slugifyWorkspaceName,
} from "~/git";

async function git(args: string[], cwd: string): Promise<void> {
  const result = await runProcessToCompletion(["git", ...args], { cwd });
  if (result.exitCode !== 0) {
    throw new Error(`git ${args.join(" ")} failed: ${result.stderr}`);
  }
}

describe("git branch naming helpers", () => {
  it("slugifies on a word boundary and resolves patterns", () => {
    // Exactly 20 chars: kept as-is.
    expect(slugifyWorkspaceName("My Feature Workspace")).toBe("my-feature-workspace");
    // Over 20 chars: truncated on a word boundary.
    expect(slugifyWorkspaceName("My Awesome Feature Workspace")).toBe("my-awesome-feature");
    expect(slugifyWorkspaceName("  ")).toBe("");
    expect(resolvePattern("<user>/<slug>", "dev", "feature")).toBe("dev/feature");
    // Empty user slug collapses the leading segment.
    expect(resolvePattern("<user>/<slug>", "", "feature")).toBe("feature");
  });
});

describe("git workspace setup", () => {
  let dir: string;
  let repo: string;

  beforeEach(async () => {
    dir = realpathSync(mkdtempSync(path.join(tmpdir(), "sculptor-git-")));
    repo = path.join(dir, "repo");
    await runProcessToCompletion(["git", "init", "-b", "main", repo]);
    await git(["config", "user.email", "dev@example.com"], repo);
    await git(["config", "user.name", "Dev Person"], repo);
    writeFileSync(path.join(repo, "README.md"), "hello");
    await git(["add", "."], repo);
    await git(["commit", "-m", "initial"], repo);
  });

  afterEach(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  it("revParseHead, currentBranch, branchExists report repo state", async () => {
    expect(await currentBranch(repo)).toBe("main");
    expect((await revParseHead(repo)).length).toBe(40);
    expect(await branchExists(repo, "main")).toBe(true);
    expect(await branchExists(repo, "nope")).toBe(false);
  });

  it("worktree setup creates a worktree on a new branch at the captured hash", async () => {
    const root = path.join(dir, "workspaces", "ws-abc");
    const baseHash = await revParseHead(repo);
    const result = await setupWorkspace({
      root,
      strategy: "WORKTREE",
      repoHostPath: repo,
      sourceBranch: "main",
      requestedBranchName: "dev/feature",
    });
    expect(result.workingDirectory).toBe(path.join(root, "code"));
    expect(result.sourceGitHash).toBe(baseHash);
    expect(await currentBranch(result.workingDirectory)).toBe("dev/feature");
    // The new branch appears in the user's shared .git.
    expect(await branchExists(repo, "dev/feature")).toBe(true);
  });

  it("clone setup creates an isolated working dir sharing objects", async () => {
    const root = path.join(dir, "workspaces", "ws-clone");
    const result = await setupWorkspace({ root, strategy: "CLONE", repoHostPath: repo, sourceBranch: "main" });
    expect(result.workingDirectory).toBe(path.join(root, "code"));
    expect((await revParseHead(result.workingDirectory)).length).toBe(40);
    // The clone shares objects via --reference (an alternates file exists).
    expect(await branchExists(result.workingDirectory, "main")).toBe(true);
  });

  it("in-place setup uses the repo path and captures its hash", async () => {
    const result = await setupWorkspace({ root: "/unused", strategy: "IN_PLACE", repoHostPath: repo });
    expect(result.workingDirectory).toBe(repo);
    expect(result.sourceGitHash).toBe(await revParseHead(repo));
  });

  it("previewBranchName resolves against git config user.name", async () => {
    expect(await previewBranchName({ strategy: "IN_PLACE", repoHostPath: repo, workspaceName: "x" })).toBe("");
    expect(
      await previewBranchName({ strategy: "WORKTREE", repoHostPath: repo, workspaceName: "Cool Thing" }),
    ).toBe("dev/cool-thing");
  });
});
