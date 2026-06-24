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

async function fetchGithub(
  workspaceId: string,
  branch: string,
  cwd: string,
  runner: CliRunner,
): Promise<PrStatusInfo> {
  const result = await runCli(
    [
      "gh",
      "pr",
      "list",
      "--head",
      branch,
      "--state",
      "all",
      "--json",
      "number,title,url,state,mergeable,statusCheckRollup",
    ],
    cwd,
    runner,
  );
  const prs = JSON.parse(result.stdout || "[]") as Array<
    Record<string, unknown>
  >;
  if (prs.length === 0) {
    return { workspace_id: workspaceId, pr_state: "none" };
  }
  const pr = prs[0]!;
  const state = String(pr.state ?? "").toUpperCase();
  const prState: PrState =
    state === "MERGED" ? "merged" : state === "CLOSED" ? "closed" : "open";
  const rollup = Array.isArray(pr.statusCheckRollup)
    ? (pr.statusCheckRollup[0] as { state?: string } | undefined)
    : undefined;
  return {
    workspace_id: workspaceId,
    pr_state: prState,
    pr_iid: typeof pr.number === "number" ? pr.number : null,
    pr_title: typeof pr.title === "string" ? pr.title : null,
    pr_web_url: typeof pr.url === "string" ? pr.url : null,
    has_conflicts: mergeableToConflicts(pr.mergeable as string | undefined),
    pipeline_status: rollupToPipeline(rollup?.state),
  };
}

async function fetchGitlab(
  workspaceId: string,
  branch: string,
  cwd: string,
  runner: CliRunner,
): Promise<PrStatusInfo> {
  const result = await runCli(
    ["glab", "mr", "list", "--source-branch", branch, "-F", "json"],
    cwd,
    runner,
  );
  const mrs = JSON.parse(result.stdout || "[]") as Array<
    Record<string, unknown>
  >;
  if (mrs.length === 0) {
    return { workspace_id: workspaceId, pr_state: "none" };
  }
  const mr = mrs[0]!;
  const state = String(mr.state ?? "").toLowerCase();
  const prState: PrState =
    state === "merged" ? "merged" : state === "closed" ? "closed" : "open";
  return {
    workspace_id: workspaceId,
    pr_state: prState,
    pr_iid: typeof mr.iid === "number" ? mr.iid : null,
    pr_title: typeof mr.title === "string" ? mr.title : null,
    pr_web_url: typeof mr.web_url === "string" ? mr.web_url : null,
  };
}

// Fetch status, converting any CLI failure into a PrStatusInfo carrying the
// distinct error_category (REQ-INT-003) rather than throwing.
export async function fetchPrStatus(
  provider: GitProvider,
  workspaceId: string,
  branch: string,
  cwd: string,
  runner: CliRunner,
): Promise<PrStatusInfo> {
  try {
    return provider === "github"
      ? await fetchGithub(workspaceId, branch, cwd, runner)
      : await fetchGitlab(workspaceId, branch, cwd, runner);
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
