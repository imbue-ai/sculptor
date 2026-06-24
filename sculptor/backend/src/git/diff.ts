import { runProcessToCompletion } from "~/environment/process";
import { runGit } from "~/git/git";

// The workspace diff is the RAW unified-diff text (DiffArtifact in
// interfaces/agents/artifacts.py) — the frontend counts lines to gate at >500
// (REQ-NFR-050); there is no backend line-count field. Field names/structure
// are the frontend contract (RW-API-3).

const DEFAULT_DIFF_CONTEXT_LINES = 3;

// Produces a unified diff for every untracked file so new (un-added) files
// appear in the diff, mirroring _UNTRACKED_FILES_DIFF_CMD.
const UNTRACKED_FILES_DIFF_CMD =
  "git ls-files --others --exclude-standard -z" +
  " | xargs -0 -I {} find {} -maxdepth 0 -type f -print0" +
  " | xargs -0 -I {} git --no-pager diff --no-index /dev/null {}";

const COMMIT_HASH_PATTERN = /^[0-9a-fA-F]{4,40}$/;

export interface DiffArtifact {
  object_type: "DiffArtifact";
  uncommitted_diff: string;
  target_branch_diff: string;
  target_branch_merge_base: string;
  file_errors: Record<string, string>;
}

export interface WorkspaceDiffParams {
  workingDir: string;
  contextLines?: number;
  // When set, also compute the diff from merge-base(target, HEAD) to the
  // working tree (scope=vs-target-branch).
  targetBranch?: string | null;
}

export class InvalidCommitError extends Error {
  constructor(public readonly commitHash: string) {
    super(`Invalid commit hash: ${commitHash}`);
    this.name = "InvalidCommitError";
  }
}

export interface CommitDiffResult {
  diff: string;
  commit_hash: string;
  parent_hash: string | null;
}

async function getMergeBase(workingDir: string, targetBranch: string): Promise<string | null> {
  const result = await runGit(["merge-base", "HEAD", targetBranch], workingDir);
  if (result.exitCode !== 0 || result.stdout.trim() === "") {
    return null;
  }
  return result.stdout.trim();
}

async function diffAgainst(workingDir: string, baseRef: string, contextFlag: string): Promise<string> {
  const result = await runProcessToCompletion(
    ["bash", "-c", `git --no-pager diff -M ${contextFlag} ${baseRef}; ${UNTRACKED_FILES_DIFF_CMD}`],
    { cwd: workingDir },
  );
  return result.stdout.trim();
}

// uncommitted_diff = working tree vs HEAD + untracked files; target_branch_diff
// = merge-base(target, HEAD) vs working tree. Mirrors _create_diff_artifact_local.
export async function workspaceDiff(params: WorkspaceDiffParams): Promise<DiffArtifact> {
  const contextLines = params.contextLines ?? DEFAULT_DIFF_CONTEXT_LINES;
  const contextFlag = `-U${contextLines}`;

  const uncommittedDiff = await diffAgainst(params.workingDir, "HEAD", contextFlag);

  let targetBranchDiff = "";
  let targetBranchMergeBase = "";
  if (params.targetBranch !== undefined && params.targetBranch !== null) {
    const mergeBase = await getMergeBase(params.workingDir, params.targetBranch);
    if (mergeBase !== null) {
      targetBranchMergeBase = mergeBase;
      targetBranchDiff = await diffAgainst(params.workingDir, mergeBase, contextFlag);
    }
  }

  return {
    object_type: "DiffArtifact",
    uncommitted_diff: uncommittedDiff,
    target_branch_diff: targetBranchDiff,
    target_branch_merge_base: targetBranchMergeBase,
    file_errors: {},
  };
}

// The unified diff for a single commit (base = its parent, or the root for the
// initial commit). Mirrors get_commit_diff.
export async function commitDiff(workingDir: string, commitHash: string): Promise<CommitDiffResult> {
  if (!COMMIT_HASH_PATTERN.test(commitHash)) {
    throw new InvalidCommitError(commitHash);
  }
  const typeResult = await runGit(["cat-file", "-t", commitHash], workingDir);
  if (typeResult.exitCode !== 0 || typeResult.stdout.trim() !== "commit") {
    throw new InvalidCommitError(commitHash);
  }

  const resolveResult = await runGit(["rev-parse", commitHash], workingDir);
  const resolvedHash =
    resolveResult.exitCode === 0 && resolveResult.stdout.trim() !== "" ? resolveResult.stdout.trim() : commitHash;

  const parentResult = await runGit(["rev-parse", `${resolvedHash}^`], workingDir);
  const parentHash =
    parentResult.exitCode === 0 && parentResult.stdout.trim() !== "" ? parentResult.stdout.trim() : null;

  const diffArgs =
    parentHash !== null
      ? ["--no-pager", "diff", "-M", `${parentHash}..${resolvedHash}`]
      : ["--no-pager", "diff-tree", "-p", "--root", "-M", resolvedHash];
  const diffResult = await runGit(diffArgs, workingDir);
  const diff = diffResult.exitCode !== null && diffResult.exitCode <= 1 ? diffResult.stdout : "";

  return { diff, commit_hash: resolvedHash, parent_hash: parentHash };
}
