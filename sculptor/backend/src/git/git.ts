import { type ProcessResult, runProcessToCompletion } from "~/environment/process";

// Typed wrapper around the system `git` binary (REQ-COMPAT-021 — git is already
// required; no native libgit2 binding). Shells out via the Task 3.1 process
// helper so cwd/env handling stays consistent.

export class GitCommandError extends Error {
  constructor(
    public readonly args: readonly string[],
    public readonly exitCode: number | null,
    public readonly stderr: string,
  ) {
    super(`git ${args.join(" ")} failed (exit ${exitCode}): ${stderr.trim()}`);
    this.name = "GitCommandError";
  }
}

// Non-throwing git runner for read-side ops where a non-zero exit is expected
// (e.g. `git diff` returns 1 for a non-empty diff). Callers inspect exitCode.
export function runGit(args: readonly string[], cwd: string): Promise<ProcessResult> {
  return runProcessToCompletion(["git", ...args], { cwd });
}

async function git(args: readonly string[], cwd?: string): Promise<string> {
  const result = await runProcessToCompletion(["git", ...args], cwd === undefined ? {} : { cwd });
  if (result.exitCode !== 0) {
    throw new GitCommandError(args, result.exitCode, result.stderr);
  }
  return result.stdout;
}

export async function revParseHead(cwd: string): Promise<string> {
  return (await git(["rev-parse", "HEAD"], cwd)).trim();
}

export async function currentBranch(cwd: string): Promise<string> {
  return (await git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)).trim();
}

export async function branchExists(cwd: string, branch: string): Promise<boolean> {
  const result = await runProcessToCompletion(["git", "rev-parse", "--verify", "--quiet", `refs/heads/${branch}`], {
    cwd,
  });
  return result.exitCode === 0;
}

export async function createBranch(cwd: string, branch: string, startPoint?: string): Promise<void> {
  await git(["checkout", "-b", branch, ...(startPoint === undefined ? [] : [startPoint])], cwd);
}

export async function checkout(cwd: string, ref: string): Promise<void> {
  await git(["checkout", ref], cwd);
}

// `git -C <repo> worktree add -b <branch> <dest> <baseRef>` — a real worktree
// sharing the user's .git, so the new branch appears in the user's git state.
export async function addWorktree(
  userRepoPath: string,
  destination: string,
  newBranch: string,
  baseRef: string,
): Promise<void> {
  await git(["-C", userRepoPath, "worktree", "add", "-b", newBranch, destination, baseRef]);
}

export async function removeWorktree(userRepoPath: string, destination: string): Promise<void> {
  await git(["-C", userRepoPath, "worktree", "remove", "--force", destination]);
}

// Clone sharing the source's object store via --reference (isolated working
// dir, shared objects). NOTE: this is simplified vs the Python clone_strategy's
// full multi-remote replay — the clone's origin points at the local source.
// Full remote mirroring for the opt-in/off-by-default clone mode is refined
// when Phase 6 wires it.
export async function cloneShared(sourceRepoPath: string, destination: string, targetBranch?: string): Promise<void> {
  await git(["clone", "--reference", sourceRepoPath, sourceRepoPath, destination]);
  if (targetBranch !== undefined) {
    await checkout(destination, targetBranch);
  }
}
