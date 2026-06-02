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
the auto-generated branch when a WORKTREE workspace is deleted."""


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
    logger.info(
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
    logger.info("Successfully created worktree at {} on branch {}", destination, new_branch)


def remove_worktree(
    user_repo_path: Path,
    destination: Path,
    branch_name: str,
    deletion_policy: DeletionPolicy,
    concurrency_group: ConcurrencyGroup,
) -> None:
    """Remove the worktree at `destination` and apply `deletion_policy` to `branch_name`.

    Never raises: worktree deletion must always make progress. Failures from
    `git worktree remove` (e.g. user already removed it manually) and from
    branch deletion (e.g. unmerged branch under `delete_if_safe`) are logged
    and swallowed.
    """
    logger.info(
        "Removing worktree at {} (branch {}, policy {}, user repo: {})",
        destination,
        branch_name,
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
        logger.info("git worktree remove failed, continuing: {}", e)

    if deletion_policy == "never":
        return

    branch_flag = "-d" if deletion_policy == "delete_if_safe" else "-D"
    try:
        _run_git_command(
            ["git", "-C", str(user_repo_path), "branch", branch_flag, branch_name],
            cwd=None,
            concurrency_group=concurrency_group,
            error_message=f"Failed to delete branch {branch_name} with policy {deletion_policy}",
        )
    except WorktreeError as e:
        logger.info("Branch deletion failed (policy {}), continuing: {}", deletion_policy, e)


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
