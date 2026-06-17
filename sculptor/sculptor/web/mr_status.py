import json
from pathlib import Path
from typing import Literal

from loguru import logger

from sculptor.primitives.ids import WorkspaceID
from sculptor.web.cli_status_utils import CliStatusError
from sculptor.web.cli_status_utils import classify_cli_error
from sculptor.web.cli_status_utils import run_cli_with_retry
from sculptor.web.cli_status_utils import strip_remote_prefix
from sculptor.web.derived import PrApproval
from sculptor.web.derived import PrComment
from sculptor.web.derived import PrStatusInfo


def fetch_mr_status(
    workspace_id: WorkspaceID,
    working_dir: Path,
    current_branch: str,
    target_branch: str,
) -> PrStatusInfo:
    """Fetch MR status from GitLab for a workspace's current and target branch.

    Calls the glab CLI to find an open or merged MR matching the branches,
    and if found, fetches pipeline info, approvals, and unresolved comments.

    If no open MR matches the exact source+target pair but an open MR exists
    on the source branch targeting a different branch, the mismatch fields
    are populated so the frontend can warn the user.

    Returns a PrStatusInfo with error_category set if the CLI is missing
    or returns a classifiable error. The caller is responsible for
    verifying the origin is GitLab before calling this function.
    """
    try:
        return _fetch_mr_status_inner(workspace_id, working_dir, current_branch, target_branch)
    except CliStatusError as e:
        logger.debug("MR status check failed ({}): {}", e.category, e)
        return PrStatusInfo(
            workspace_id=workspace_id,
            pr_state="none",
            error_category=e.category,
            error_provider="gitlab",
            error_message=str(e),
        )


def _fetch_mr_status_inner(
    workspace_id: WorkspaceID,
    working_dir: Path,
    current_branch: str,
    target_branch: str,
) -> PrStatusInfo:
    """Inner implementation that raises CliStatusError on CLI failures."""
    stripped_target = strip_remote_prefix(target_branch)

    # Search for open MRs on this source branch (without target filter)
    open_mrs = _find_open_mrs(working_dir, current_branch)

    # Look for an exact target match among open MRs
    mr_data = None
    mismatched_mr = None
    for mr in open_mrs:
        if mr.get("target_branch") == stripped_target:
            mr_data = mr
            break
    else:
        # No exact match — use the first open MR as a mismatch candidate
        if open_mrs:
            mismatched_mr = open_mrs[0]

    if mr_data is not None:
        return _build_open_mr_status(workspace_id, working_dir, mr_data)

    # No open MR matches — check for merged MR with exact target match
    merged_data = _find_merged_mr(working_dir, current_branch, stripped_target)
    if merged_data is not None:
        return PrStatusInfo(
            workspace_id=workspace_id,
            pr_state="merged",
            pr_iid=merged_data["iid"],
            pr_title=merged_data.get("title"),
            pr_web_url=merged_data.get("web_url"),
        )

    # Then check for a closed-not-merged MR with exact target match
    closed_data = _find_closed_mr(working_dir, current_branch, stripped_target)
    if closed_data is not None:
        return PrStatusInfo(
            workspace_id=workspace_id,
            pr_state="closed",
            pr_iid=closed_data["iid"],
            pr_title=closed_data.get("title"),
            pr_web_url=closed_data.get("web_url"),
        )

    # No matching MR at all — return mismatch info if we found one
    if mismatched_mr is not None:
        return PrStatusInfo(
            workspace_id=workspace_id,
            pr_state="none",
            mismatched_pr_iid=mismatched_mr["iid"],
            mismatched_pr_target_branch=mismatched_mr.get("target_branch"),
            mismatched_pr_web_url=mismatched_mr.get("web_url"),
        )

    return PrStatusInfo(workspace_id=workspace_id, pr_state="none")


def _build_open_mr_status(
    workspace_id: WorkspaceID,
    working_dir: Path,
    mr_data: dict,
) -> PrStatusInfo:
    """Build a full PrStatusInfo for an open MR (pipeline, approvals, comments)."""
    mr_iid = mr_data["iid"]
    pipeline_status, pipeline_id, pipeline_web_url, pipeline_updated_at = _fetch_pipeline_info(working_dir, mr_iid)
    approvals = _fetch_approvals(working_dir, mr_iid)
    unresolved_comments = _fetch_unresolved_comments(working_dir, mr_iid)

    return PrStatusInfo(
        workspace_id=workspace_id,
        pr_state="open",
        has_conflicts=mr_data.get("has_conflicts"),
        pr_iid=mr_iid,
        pr_title=mr_data.get("title"),
        pr_web_url=mr_data.get("web_url"),
        pipeline_status=pipeline_status,
        pipeline_id=pipeline_id,
        pipeline_web_url=pipeline_web_url,
        pipeline_updated_at=pipeline_updated_at,
        approvals=approvals,
        unresolved_comments=unresolved_comments,
    )


def _find_open_mrs(working_dir: Path, source_branch: str) -> list[dict]:
    """Find open MRs for a source branch (no target filter). Returns up to 5."""
    cmd = [
        "glab",
        "mr",
        "list",
        f"--source-branch={source_branch}",
        "-F",
        "json",
        "--per-page",
        "5",
    ]
    result = run_cli_with_retry(cmd, working_dir)
    if result.returncode != 0:
        raise CliStatusError(classify_cli_error(result.stderr), result.stderr)
    try:
        mrs = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise CliStatusError("transient", f"Invalid JSON from glab mr list: {result.stdout[:200]}") from e
    return mrs


def _find_merged_mr(working_dir: Path, source_branch: str, target_branch: str) -> dict | None:
    """Find a merged MR matching the exact source+target pair."""
    cmd = [
        "glab",
        "mr",
        "list",
        f"--source-branch={source_branch}",
        f"--target-branch={target_branch}",
        "--merged",
        "-F",
        "json",
        "--per-page",
        "1",
    ]
    result = run_cli_with_retry(cmd, working_dir)
    if result.returncode != 0:
        raise CliStatusError(classify_cli_error(result.stderr), result.stderr)
    try:
        mrs = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise CliStatusError("transient", f"Invalid JSON from glab mr list: {result.stdout[:200]}") from e
    if not mrs:
        return None
    return mrs[0]


def _find_closed_mr(working_dir: Path, source_branch: str, target_branch: str) -> dict | None:
    """Find a closed-not-merged MR matching the exact source+target pair."""
    cmd = [
        "glab",
        "mr",
        "list",
        f"--source-branch={source_branch}",
        f"--target-branch={target_branch}",
        "--closed",
        "-F",
        "json",
        "--per-page",
        "1",
    ]
    result = run_cli_with_retry(cmd, working_dir)
    if result.returncode != 0:
        raise CliStatusError(classify_cli_error(result.stderr), result.stderr)
    try:
        mrs = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise CliStatusError("transient", f"Invalid JSON from glab mr list: {result.stdout[:200]}") from e
    if not mrs:
        return None
    return mrs[0]


def _normalize_pipeline_status(raw_status: str | None) -> Literal["running", "passed", "failed"] | None:
    """Map GitLab pipeline status strings to our simplified three-state model."""
    if raw_status is None:
        return None
    if raw_status == "success":
        return "passed"
    if raw_status in ("failed", "canceled"):
        return "failed"
    if raw_status in ("running", "pending", "created", "preparing", "waiting_for_resource", "scheduled", "manual"):
        return "running"
    return None


def _fetch_pipeline_info(
    working_dir: Path, mr_iid: int
) -> tuple[Literal["running", "passed", "failed"] | None, int | None, str | None, str | None]:
    result = run_cli_with_retry(["glab", "mr", "view", str(mr_iid), "-F", "json"], working_dir)
    if result.returncode != 0:
        logger.debug("glab mr view failed: {}", result.stderr)
        return None, None, None, None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        logger.debug("Invalid JSON from glab mr view: {}", result.stdout[:200])
        return None, None, None, None
    pipeline = data.get("pipeline")
    if pipeline is None:
        return None, None, None, None
    status = _normalize_pipeline_status(pipeline.get("status"))
    return status, pipeline.get("id"), pipeline.get("web_url"), pipeline.get("updated_at")


def _fetch_approvals(working_dir: Path, mr_iid: int) -> list[PrApproval]:
    result = run_cli_with_retry(["glab", "api", f"projects/:id/merge_requests/{mr_iid}/approvals"], working_dir)
    if result.returncode != 0:
        logger.debug("glab api approvals failed: {}", result.stderr)
        return []
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        logger.debug("Invalid JSON from glab api approvals: {}", result.stdout[:200])
        return []
    approved_by = data.get("approved_by", [])
    approvals: list[PrApproval] = []
    for entry in approved_by:
        user = entry.get("user", {})
        name = user.get("name", user.get("username", "unknown"))
        approvals.append(PrApproval(name=name, approved=True))
    return approvals


def _fetch_unresolved_comments(working_dir: Path, mr_iid: int) -> list[PrComment]:
    result = run_cli_with_retry(["glab", "api", f"projects/:id/merge_requests/{mr_iid}/discussions"], working_dir)
    if result.returncode != 0:
        logger.debug("glab api discussions failed: {}", result.stderr)
        return []
    try:
        discussions = json.loads(result.stdout)
    except json.JSONDecodeError:
        logger.debug("Invalid JSON from glab api discussions: {}", result.stdout[:200])
        return []
    comments: list[PrComment] = []
    for discussion in discussions:
        notes = discussion.get("notes", [])
        for note in notes:
            if note.get("resolvable") and not note.get("resolved"):
                position = note.get("position", {})
                comments.append(
                    PrComment(
                        author=note.get("author", {}).get("name", "unknown"),
                        file_path=position.get("new_path", ""),
                        line=position.get("new_line"),
                        body=note.get("body", ""),
                    )
                )
    return comments
