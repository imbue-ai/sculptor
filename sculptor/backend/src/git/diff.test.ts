import { mkdtempSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { runProcessToCompletion } from "~/environment/process";
import {
  commitDiff,
  discardFile,
  InvalidCommitError,
  listCommits,
  PathEscapesWorkspaceError,
  readFileAtRef,
  revParseHead,
  workspaceDiff,
} from "~/git";

async function git(args: string[], cwd: string): Promise<string> {
  const result = await runProcessToCompletion(["git", ...args], { cwd });
  if (result.exitCode !== 0) {
    throw new Error(`git ${args.join(" ")} failed: ${result.stderr}`);
  }
  return result.stdout;
}

describe("git read-side ops", () => {
  let dir: string;
  let repo: string;
  let baseHash: string;

  beforeEach(async () => {
    dir = realpathSync(mkdtempSync(path.join(tmpdir(), "sculptor-diff-")));
    repo = path.join(dir, "repo");
    await runProcessToCompletion(["git", "init", "-b", "main", repo]);
    await git(["config", "user.email", "dev@example.com"], repo);
    await git(["config", "user.name", "Dev Person"], repo);
    writeFileSync(path.join(repo, "a.txt"), "one\n");
    await git(["add", "."], repo);
    await git(["commit", "-m", "first"], repo);
    baseHash = (await revParseHead(repo)).trim();
    writeFileSync(path.join(repo, "a.txt"), "one\ntwo\n");
    await git(["commit", "-am", "second"], repo);
  });

  afterEach(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  it("workspaceDiff captures uncommitted edits and untracked files", async () => {
    writeFileSync(path.join(repo, "a.txt"), "one\ntwo\nthree\n");
    writeFileSync(path.join(repo, "new.txt"), "fresh\n");
    const diff = await workspaceDiff({ workingDir: repo });
    expect(diff.object_type).toBe("DiffArtifact");
    expect(diff.uncommitted_diff).toContain("a.txt");
    expect(diff.uncommitted_diff).toContain("+three");
    // Untracked file appears as a new-file diff.
    expect(diff.uncommitted_diff).toContain("new.txt");
    expect(diff.uncommitted_diff).toContain("+fresh");
  });

  it("listCommits returns commits since the base with file stats", async () => {
    const history = await listCommits({ workingDir: repo, sourceGitHash: baseHash });
    expect(history.fork_point).toBe(baseHash);
    expect(history.commits.map((c) => c.message)).toEqual(["second"]);
    const second = history.commits[0]!;
    expect(second.files).toEqual([{ path: "a.txt", status: "M", old_path: null, additions: 1, deletions: 0 }]);
    expect(second.short_hash.length).toBeGreaterThan(0);
  });

  it("commitDiff matches git show and resolves the parent", async () => {
    const head = (await revParseHead(repo)).trim();
    const result = await commitDiff(repo, head);
    expect(result.commit_hash).toBe(head);
    expect(result.parent_hash).toBe(baseHash);
    expect(result.diff).toContain("+two");
    await expect(commitDiff(repo, "zzzz")).rejects.toBeInstanceOf(InvalidCommitError);
  });

  it("readFileAtRef returns historical contents", async () => {
    expect(await readFileAtRef(repo, baseHash, "a.txt")).toBe("one\n");
    expect(await readFileAtRef(repo, "HEAD", "a.txt")).toBe("one\ntwo\n");
  });

  it("discardFile reverts a tracked file and rejects path escapes", async () => {
    writeFileSync(path.join(repo, "a.txt"), "tampered\n");
    await discardFile(repo, "a.txt");
    expect(await readFileAtRef(repo, "HEAD", "a.txt")).toBe("one\ntwo\n");
    await expect(discardFile(repo, "../escape.txt")).rejects.toBeInstanceOf(PathEscapesWorkspaceError);
  });
});
