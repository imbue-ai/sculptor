"""Git worktree operations for WORKTREE-mode workspaces.

Mirrors the shape of clone_strategy.py but creates a `git worktree add`
off the user's repository (shared `.git`) instead of a full clone.
"""

from pathlib import Path
from typing import Literal

from loguru import logger

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.subprocess_utils import ProcessError

DeletionPolicy = Literal["never", "delete_if_safe", "always"]
"""Mirrors `UserConfig.workspace_branch_deletion_policy` — what to do with
the workspace's branch (the auto-generated one, or whatever it was renamed
to) when a WORKTREE workspace is deleted."""


class WorktreeError(Exception):
    """Error raised when a git worktree operation fails."""


def create_worktree(
    user_repo_path: Path,
    destination: Path,
    concurrency_group: ConcurrencyGroup,
    base_ref: str,
    new_branch: str,
) -> None:
    """Create a new git worktree at `destination` on branch `new_branch` off `base_ref`.

    The worktree shares the user's `.git` at `user_repo_path` via a gitfile
    pointer, so the new branch appears directly in the user's git state.

    Raises:
        WorktreeError: If `git worktree add` fails (e.g. missing base ref,
            branch already exists, destination already exists).
    """
    logger.debug(
        "Creating worktree at {} on branch {} from base {} (user repo: {})",
        destination,
        new_branch,
        base_ref,
        user_repo_path,
    )
    _run_git_command(
        [
            "git",
            "-C",
            str(user_repo_path),
            "worktree",
            "add",
            "-b",
            new_branch,
            str(destination),
            base_ref,
        ],
        cwd=None,
        concurrency_group=concurrency_group,
        error_message=f"Failed to create worktree at {destination} on branch {new_branch} from base {base_ref}",
    )
    logger.debug("Successfully created worktree at {} on branch {}", destination, new_branch)


def remove_worktree(
    user_repo_path: Path,
    destination: Path,
    branch_name: str,
    deletion_policy: DeletionPolicy,
    concurrency_group: ConcurrencyGroup,
) -> None:
    """Remove the worktree at `destination` and apply `deletion_policy` to its branch.

    `branch_name` is the branch the worktree was created on. When it no longer
    exists because it was renamed inside the worktree (the agent's auto-rename
    does this), the policy is applied to the branch the worktree currently has
    checked out instead. When `branch_name` still exists it is the one deleted,
    even if the worktree has since switched to some other branch: the policy only
    ever touches the branch this workspace created.

    Never raises: worktree deletion must always make progress. Failures from
    `git worktree remove` (e.g. user already removed it manually) and from
    branch deletion (e.g. unmerged branch under `delete_if_safe`) are logged
    and swallowed.
    """
    # Resolved before `git worktree remove`, which discards the worktree's HEAD.
    branch_to_delete = (
        None
        if deletion_policy == "never"
        else _resolve_branch_to_delete(user_repo_path, destination, branch_name, concurrency_group)
    )
    logger.debug(
        "Removing worktree at {} (deleting branch {}, policy {}, user repo: {})",
        destination,
        branch_to_delete,
        deletion_policy,
        user_repo_path,
    )
    try:
        _run_git_command(
            ["git", "-C", str(user_repo_path), "worktree", "remove", str(destination)],
            cwd=None,
            concurrency_group=concurrency_group,
            error_message=f"Failed to remove worktree at {destination}",
        )
    except WorktreeError as e:
        logger.debug("git worktree remove failed, continuing: {}", e)

    if branch_to_delete is None:
        return

    branch_flag = "-d" if deletion_policy == "delete_if_safe" else "-D"
    try:
        _run_git_command(
            ["git", "-C", str(user_repo_path), "branch", branch_flag, branch_to_delete],
            cwd=None,
            concurrency_group=concurrency_group,
            error_message=f"Failed to delete branch {branch_to_delete} with policy {deletion_policy}",
        )
    except WorktreeError as e:
        logger.debug("Branch deletion failed (policy {}), continuing: {}", deletion_policy, e)


def _resolve_branch_to_delete(
    user_repo_path: Path,
    destination: Path,
    created_branch: str,
    concurrency_group: ConcurrencyGroup,
) -> str | None:
    """Pick the branch the deletion policy applies to: the created one, or its rename.

    None when neither can be identified (the created branch is gone and the
    worktree's HEAD is detached or unreadable), in which case nothing is deleted.
    """
    if _local_branch_exists(user_repo_path, created_branch, concurrency_group):
        return created_branch
    checked_out = _read_checked_out_branch(destination, concurrency_group)
    if checked_out is None:
        logger.debug("Branch {} no longer exists and the worktree's branch is unknown; not deleting", created_branch)
        return None
    logger.debug(
        "Branch {} no longer exists; treating {} (checked out in the worktree) as its rename",
        created_branch,
        checked_out,
    )
    return checked_out


def _local_branch_exists(user_repo_path: Path, branch_name: str, concurrency_group: ConcurrencyGroup) -> bool:
    command = ["git", "-C", str(user_repo_path), "show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}"]
    return _run_git_query(command, concurrency_group) is not None


def _read_checked_out_branch(worktree_path: Path, concurrency_group: ConcurrencyGroup) -> str | None:
    """The branch checked out at `worktree_path`, or None if it is gone or HEAD is detached."""
    stdout = _run_git_query(["git", "-C", str(worktree_path), "symbolic-ref", "--short", "HEAD"], concurrency_group)
    if stdout is None:
        return None
    return stdout.strip()


def _run_git_query(command: list[str], concurrency_group: ConcurrencyGroup) -> str | None:
    """Run a read-only git command; return its stdout on success, None on any failure.

    Unlike `_run_git_command`, a non-zero exit is an ordinary answer here (e.g. a
    ref that does not exist), so nothing is logged at error level.
    """
    try:
        result = concurrency_group.run_process_to_completion(command, cwd=None, is_checked_after=False)
    except ProcessError as e:
        logger.debug("git query {} failed: {}", " ".join(command), e)
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _run_git_command(
    command: list[str],
    cwd: Path | None,
    concurrency_group: ConcurrencyGroup,
    error_message: str,
) -> None:
    """Run a git command; raise WorktreeError on non-zero exit."""
    logger.debug("Running git command (cwd={}): {}", cwd, " ".join(command))
    try:
        concurrency_group.run_process_to_completion(
            command,
            cwd=cwd,
            is_checked_after=True,
        )
    except ProcessError as e:
        stderr = e.stderr.strip() if e.stderr else "No error output"
        logger.error("{}: {}", error_message, stderr)
        raise WorktreeError(f"{error_message}: {stderr}") from e
