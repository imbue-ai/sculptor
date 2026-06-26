import {
  CliStatusError,
  type CliRunner,
  runCli,
} from "~/services/pr_polling/cli_status";
import type { GitProvider } from "~/services/pr_polling/provider";

// Query PR/MR status via the provider CLI and map it to a PrStatusInfo
// (snake_case, data_types.py PrStatusInfo). Camelized at the WS boundary.
// The CLI commands are the simple list forms (parity with web/pr_status.py /
// mr_status.py at the field level); the full GraphQL review/comment surface is
// a follow-up — the core pr_state + pipeline + conflict signals are mapped.

export type PrState = "none" | "open" | "merged" | "closed";
export type PipelineStatus = "running" | "passed" | "failed";

export interface PrStatusInfo {
  workspace_id: string;
  pr_state: PrState;
  has_conflicts?: boolean | null;
  pr_iid?: number | null;
  pr_title?: string | null;
  pr_web_url?: string | null;
  pipeline_status?: PipelineStatus | null;
  pipeline_id?: number | null;
  mismatched_pr_iid?: number | null;
  mismatched_pr_target_branch?: string | null;
  mismatched_pr_web_url?: string | null;
  error_category?: string | null;
  error_provider?: GitProvider | null;
  error_message?: string | null;
}

function rollupToPipeline(state: string | undefined): PipelineStatus | null {
  if (state === "FAILURE" || state === "ERROR") {
    return "failed";
  }
  if (state === "PENDING" || state === "EXPECTED") {
    return "running";
  }
  if (state === "SUCCESS") {
    return "passed";
  }
  return null;
}

function mergeableToConflicts(mergeable: string | undefined): boolean | null {
  if (mergeable === "CONFLICTING") {
    return true;
  }
  if (mergeable === "MERGEABLE") {
    return false;
  }
  return null;
}

// Strip a single remote prefix from a branch ref ("origin/main" → "main"),
// matching web/pr_status.py strip_remote_prefix.
function stripRemotePrefix(branch: string): string {
  const slash = branch.indexOf("/");
  return slash === -1 ? branch : branch.slice(slash + 1);
}

const PR_QUERY_LIMIT = 5;

// One GraphQL request returns every PR on this source branch (all states) with
// its check/conflict detail, so we group by state and dispatch locally —
// mirrors web/pr_status.py (_GRAPHQL_PR_QUERY). The simple `gh pr list` form
// doesn't carry baseRefName for target matching, so the contract uses graphql.
const GRAPHQL_PR_QUERY = `
query($owner: String!, $name: String!, $branch: String!, $limit: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequests(headRefName: $branch, first: $limit, orderBy: {field: UPDATED_AT, direction: DESC}) {
      nodes {
        number
        title
        url
        state
        baseRefName
        mergeable
        commits(last: 1) { nodes { commit { statusCheckRollup { state } } } }
      }
    }
  }
}
`;

function firstMatchingTarget(
  prs: Array<Record<string, unknown>>,
  target: string,
): Record<string, unknown> | undefined {
  return prs.find((pr) => pr.baseRefName === target);
}

function checkStatusOf(pr: Record<string, unknown>): PipelineStatus | null {
  const commitNodes = ((pr.commits as { nodes?: unknown[] } | undefined)
    ?.nodes ?? []) as Array<Record<string, unknown>>;
  if (commitNodes.length === 0) {
    return null;
  }
  const rollup = (
    (commitNodes[0]!.commit as Record<string, unknown> | undefined) ?? {}
  ).statusCheckRollup as { state?: string } | null | undefined;
  return rollupToPipeline(rollup?.state);
}

function identityStatus(
  workspaceId: string,
  prState: PrState,
  pr: Record<string, unknown>,
): PrStatusInfo {
  return {
    workspace_id: workspaceId,
    pr_state: prState,
    pr_iid: typeof pr.number === "number" ? pr.number : null,
    pr_title: typeof pr.title === "string" ? pr.title : null,
    pr_web_url: typeof pr.url === "string" ? pr.url : null,
  };
}

// A terminal-state GitLab MR (merged/closed) carries only identity fields,
// keyed by glab's `iid`/`web_url` (vs GitHub's `number`/`url`).
function gitlabIdentityStatus(
  workspaceId: string,
  prState: PrState,
  mr: Record<string, unknown>,
): PrStatusInfo {
  return {
    workspace_id: workspaceId,
    pr_state: prState,
    pr_iid: typeof mr.iid === "number" ? mr.iid : null,
    pr_title: typeof mr.title === "string" ? mr.title : null,
    pr_web_url: typeof mr.web_url === "string" ? mr.web_url : null,
  };
}

async function fetchGithub(
  workspaceId: string,
  branch: string,
  targetBranch: string,
  cwd: string,
  runner: CliRunner,
): Promise<PrStatusInfo> {
  const result = await runCli(
    [
      "gh",
      "api",
      "graphql",
      "-f",
      `query=${GRAPHQL_PR_QUERY}`,
      "-F",
      "owner={owner}",
      "-F",
      "name={repo}",
      "-f",
      `branch=${branch}`,
      "-F",
      `limit=${PR_QUERY_LIMIT}`,
    ],
    cwd,
    runner,
  );
  const payload = JSON.parse(result.stdout || "{}") as Record<string, unknown>;
  const repository = (payload.data as Record<string, unknown> | undefined)
    ?.repository as Record<string, unknown> | undefined;
  const nodes = ((repository?.pullRequests as { nodes?: unknown[] } | undefined)
    ?.nodes ?? []) as Array<Record<string, unknown>>;

  const target = stripRemotePrefix(targetBranch);
  const openPrs = nodes.filter((pr) => pr.state === "OPEN");
  const mergedPrs = nodes.filter((pr) => pr.state === "MERGED");
  const closedPrs = nodes.filter((pr) => pr.state === "CLOSED");

  // An open PR against the exact target gets the full treatment.
  const openMatch = firstMatchingTarget(openPrs, target);
  if (openMatch !== undefined) {
    return {
      workspace_id: workspaceId,
      pr_state: "open",
      pr_iid: typeof openMatch.number === "number" ? openMatch.number : null,
      pr_title: typeof openMatch.title === "string" ? openMatch.title : null,
      pr_web_url: typeof openMatch.url === "string" ? openMatch.url : null,
      has_conflicts: mergeableToConflicts(openMatch.mergeable as string),
      pipeline_status: checkStatusOf(openMatch),
    };
  }
  // Prefer a terminal state for the exact target (merged wins over closed).
  const mergedMatch = firstMatchingTarget(mergedPrs, target);
  if (mergedMatch !== undefined) {
    return identityStatus(workspaceId, "merged", mergedMatch);
  }
  const closedMatch = firstMatchingTarget(closedPrs, target);
  if (closedMatch !== undefined) {
    return identityStatus(workspaceId, "closed", closedMatch);
  }
  // An open PR against a *different* target — surface it for "switch target".
  if (openPrs.length > 0) {
    const mismatched = openPrs[0]!;
    return {
      workspace_id: workspaceId,
      pr_state: "none",
      mismatched_pr_iid:
        typeof mismatched.number === "number" ? mismatched.number : null,
      mismatched_pr_target_branch:
        typeof mismatched.baseRefName === "string"
          ? mismatched.baseRefName
          : null,
      mismatched_pr_web_url:
        typeof mismatched.url === "string" ? mismatched.url : null,
    };
  }
  return { workspace_id: workspaceId, pr_state: "none" };
}

// Map GitLab pipeline status strings to the simplified three-state model
// (web/mr_status.py _normalize_pipeline_status).
function normalizeGitlabPipeline(raw: unknown): PipelineStatus | null {
  if (raw === "success") {
    return "passed";
  }
  if (raw === "failed" || raw === "canceled") {
    return "failed";
  }
  if (
    raw === "running" ||
    raw === "pending" ||
    raw === "created" ||
    raw === "preparing" ||
    raw === "waiting_for_resource" ||
    raw === "scheduled" ||
    raw === "manual"
  ) {
    return "running";
  }
  return null;
}

async function glabMrList(
  cwd: string,
  runner: CliRunner,
  args: string[],
): Promise<Array<Record<string, unknown>>> {
  const result = await runCli(["glab", "mr", "list", ...args], cwd, runner);
  return JSON.parse(result.stdout || "[]") as Array<Record<string, unknown>>;
}

// Fetch the pipeline id/status for an open MR via `glab mr view` (web/mr_status.py
// _fetch_pipeline_info). A view failure or pipeline-less MR yields nulls.
async function fetchGitlabPipeline(
  cwd: string,
  runner: CliRunner,
  mrIid: number,
): Promise<{ status: PipelineStatus | null; id: number | null }> {
  try {
    const result = await runCli(
      ["glab", "mr", "view", String(mrIid), "-F", "json"],
      cwd,
      runner,
    );
    const data = JSON.parse(result.stdout || "{}") as Record<string, unknown>;
    const pipeline = data.pipeline as
      | Record<string, unknown>
      | null
      | undefined;
    if (pipeline === null || pipeline === undefined) {
      return { status: null, id: null };
    }
    return {
      status: normalizeGitlabPipeline(pipeline.status),
      id: typeof pipeline.id === "number" ? pipeline.id : null,
    };
  } catch {
    return { status: null, id: null };
  }
}

async function fetchGitlab(
  workspaceId: string,
  branch: string,
  targetBranch: string,
  cwd: string,
  runner: CliRunner,
): Promise<PrStatusInfo> {
  const target = stripRemotePrefix(targetBranch);
  const openMrs = await glabMrList(cwd, runner, [
    `--source-branch=${branch}`,
    "-F",
    "json",
    "--per-page",
    "5",
  ]);
  const openMatch = openMrs.find((mr) => mr.target_branch === target);
  if (openMatch !== undefined) {
    const mrIid = typeof openMatch.iid === "number" ? openMatch.iid : null;
    const pipeline =
      mrIid !== null
        ? await fetchGitlabPipeline(cwd, runner, mrIid)
        : { status: null, id: null };
    return {
      workspace_id: workspaceId,
      pr_state: "open",
      has_conflicts:
        typeof openMatch.has_conflicts === "boolean"
          ? openMatch.has_conflicts
          : null,
      pr_iid: mrIid,
      pr_title: typeof openMatch.title === "string" ? openMatch.title : null,
      pr_web_url:
        typeof openMatch.web_url === "string" ? openMatch.web_url : null,
      pipeline_status: pipeline.status,
      pipeline_id: pipeline.id,
    };
  }

  // No open MR matches the exact target — check a merged, then a closed, MR.
  const mergedMrs = await glabMrList(cwd, runner, [
    `--source-branch=${branch}`,
    `--target-branch=${target}`,
    "--merged",
    "-F",
    "json",
    "--per-page",
    "1",
  ]);
  if (mergedMrs.length > 0) {
    return gitlabIdentityStatus(workspaceId, "merged", mergedMrs[0]!);
  }
  const closedMrs = await glabMrList(cwd, runner, [
    `--source-branch=${branch}`,
    `--target-branch=${target}`,
    "--closed",
    "-F",
    "json",
    "--per-page",
    "1",
  ]);
  if (closedMrs.length > 0) {
    return gitlabIdentityStatus(workspaceId, "closed", closedMrs[0]!);
  }

  // An open MR against a *different* target — surface it for "switch target".
  if (openMrs.length > 0) {
    const mismatched = openMrs[0]!;
    return {
      workspace_id: workspaceId,
      pr_state: "none",
      mismatched_pr_iid:
        typeof mismatched.iid === "number" ? mismatched.iid : null,
      mismatched_pr_target_branch:
        typeof mismatched.target_branch === "string"
          ? mismatched.target_branch
          : null,
      mismatched_pr_web_url:
        typeof mismatched.web_url === "string" ? mismatched.web_url : null,
    };
  }
  return { workspace_id: workspaceId, pr_state: "none" };
}

// Fetch status, converting any CLI failure into a PrStatusInfo carrying the
// distinct error_category rather than throwing.
export async function fetchPrStatus(
  provider: GitProvider,
  workspaceId: string,
  branch: string,
  targetBranch: string,
  cwd: string,
  runner: CliRunner,
): Promise<PrStatusInfo> {
  try {
    return provider === "github"
      ? await fetchGithub(workspaceId, branch, targetBranch, cwd, runner)
      : await fetchGitlab(workspaceId, branch, targetBranch, cwd, runner);
  } catch (error) {
    if (error instanceof CliStatusError) {
      return {
        workspace_id: workspaceId,
        pr_state: "none",
        error_category: error.category,
        error_provider: provider,
        error_message: error.stderr.slice(0, 500),
      };
    }
    // Malformed JSON or unexpected shape — non-actionable, surfaced as transient.
    return {
      workspace_id: workspaceId,
      pr_state: "none",
      error_category: "transient",
      error_provider: provider,
      error_message: error instanceof Error ? error.message : String(error),
    };
  }
}
