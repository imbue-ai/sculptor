"""Clone strategy module for creating isolated repository clones.

This module provides functionality to clone a repository with git object sharing
using --reference. The clone's git remote layout mirrors the source: every
source remote is carried over with all its ``remote.<name>.*`` config keys,
all ``refs/remotes/*`` are pre-populated, and the checked-out branch's
upstream matches the source's. When the source has no remotes, a single
``origin`` remote pointing at the source path on disk is created as a
fallback so that merge-base / diff against ``origin/<branch>`` continues to
work.
"""

import re
import shlex
from pathlib import Path

from loguru import logger

from imbue_core.concurrency_group import ConcurrencyGroup
from imbue_core.subprocess_utils import ProcessError


class CloneError(Exception):
    """Error raised when cloning a repository fails."""


def clone_repository(
    source_repo_path: Path,
    destination: Path,
    concurrency_group: ConcurrencyGroup,
    target_branch: str | None = None,
) -> None:
    """Clone a repository with object sharing and a remote layout that mirrors the source.

    Uses ``git clone --reference`` to share git objects with the source
    repository, saving disk space and time. Every remote defined in the
    source repo is carried over with its full config; if the source has no
    remotes, a single ``origin`` remote pointing at the source path on disk
    is created. All ``refs/remotes/*`` are pre-populated from the source
    (or, in the fallback case, from the source's local branches) so that
    merge-base / diff against ``origin/<branch>`` works without a fetch.

    Args:
        source_repo_path: Path to the source repository to clone from.
        destination: Path where the clone will be created.
        concurrency_group: Concurrency group for process management.
        target_branch: Branch to checkout after cloning. If None, uses the source's current branch.

    Raises:
        CloneError: If cloning fails or git operations encounter errors.
    """
    logger.info("Cloning repository from {} to {}", source_repo_path, destination)

    source_remotes = _list_remotes(source_repo_path, concurrency_group)
    branch_to_checkout = target_branch or _get_current_branch(source_repo_path, concurrency_group)

    # ``git clone --reference`` rejects worktrees ("reference repository ... as
    # a linked checkout is not supported yet"). The worktree's object store
    # lives in its parent repo, which is the correct ``--reference`` target
    # anyway. Other operations below operate via ``git -C <worktree>`` and
    # work fine because config/refs are shared with the parent.
    reference_repo_path = _resolve_worktree_to_parent(source_repo_path, concurrency_group)
    _run_git_command(
        [
            "git",
            "clone",
            "--reference",
            str(reference_repo_path),
            "--no-origin",
            str(source_repo_path),
            str(destination),
        ],
        cwd=None,
        concurrency_group=concurrency_group,
        error_message="Failed to clone repository from local path",
    )

    # Git versions prior to ~2.42 ignore ``--no-origin`` for local clones and
    # create an ``origin`` remote anyway, populating ``refs/remotes/origin/*``
    # from the clone source's local branches. Remove any such auto-created
    # remote so we start from a clean slate before replaying source's real
    # remote config. ``git remote remove`` also removes the associated
    # ``refs/remotes/<name>/*`` tracking refs.
    _remove_all_remotes(destination, concurrency_group)

    if source_remotes:
        for remote_name in source_remotes:
            _replay_remote_config(source_repo_path, destination, remote_name, concurrency_group)
        _copy_remote_refs(source_repo_path, destination, concurrency_group)
    else:
        _set_fallback_origin(destination, source_repo_path, concurrency_group)
        _copy_local_branches_as_origin_refs(source_repo_path, destination, concurrency_group)

    if branch_to_checkout:
        _ensure_target_branch_resolvable_in_clone(source_repo_path, destination, branch_to_checkout, concurrency_group)
        _run_git_command(
            ["git", "checkout", branch_to_checkout],
            cwd=destination,
            concurrency_group=concurrency_group,
            error_message=f"Failed to checkout branch {branch_to_checkout}",
        )
        _mirror_branch_upstream(source_repo_path, destination, branch_to_checkout, concurrency_group)

    logger.info("Successfully cloned repository to {} on branch {}", destination, branch_to_checkout)


def _resolve_worktree_to_parent(repo_path: Path, concurrency_group: ConcurrencyGroup) -> Path:
    """Return the parent repo path if ``repo_path`` is a worktree, else ``repo_path`` unchanged.

    A worktree's ``.git`` is a file containing ``gitdir: <parent>/.git/worktrees/<name>``.
    We detect that shape, then ask git for the canonical common-dir and walk
    one level up to the parent repo's working tree.
    """
    git_marker = repo_path / ".git"
    if not git_marker.is_file():
        return repo_path

    try:
        result = concurrency_group.run_process_to_completion(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=repo_path,
            is_checked_after=True,
        )
    except ProcessError:
        return repo_path

    common_dir = Path(result.stdout.strip())
    if not common_dir.exists():
        return repo_path
    return common_dir.parent


def _list_remotes(repo_path: Path, concurrency_group: ConcurrencyGroup) -> list[str]:
    """Return the names of every remote defined in the source repository.

    Returns an empty list if the source has no remotes or if ``git remote``
    fails for any other reason — an empty source repo is still a valid
    starting point for a clone.
    """
    try:
        result = concurrency_group.run_process_to_completion(
            ["git", "remote"],
            cwd=repo_path,
            is_checked_after=True,
        )
    except ProcessError:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _get_current_branch(repo_path: Path, concurrency_group: ConcurrencyGroup) -> str | None:
    """Get the current branch name, or None if in detached HEAD state."""
    try:
        result = concurrency_group.run_process_to_completion(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_path,
            is_checked_after=True,
        )
        branch = result.stdout.strip()
        # In detached HEAD state, this returns "HEAD"
        if branch == "HEAD":
            return None
        return branch
    except ProcessError:
        return None


def _remove_all_remotes(destination: Path, concurrency_group: ConcurrencyGroup) -> None:
    """Remove every remote configured on the clone, along with its tracking refs.

    Used to clean up any remote that ``git clone`` created implicitly before
    we replay the source's real remote configuration.
    """
    for remote_name in _list_remotes(destination, concurrency_group):
        _run_git_command(
            ["git", "remote", "remove", remote_name],
            cwd=destination,
            concurrency_group=concurrency_group,
            error_message=f"Failed to remove auto-created remote {remote_name} from clone",
        )


def _replay_remote_config(
    source_repo_path: Path,
    destination: Path,
    remote_name: str,
    concurrency_group: ConcurrencyGroup,
) -> None:
    """Replay every ``remote.<remote_name>.*`` config key from source onto the clone.

    Uses ``git config --add`` so multi-valued keys (e.g. multiple
    ``remote.origin.fetch`` refspecs) are preserved in order.
    """
    pattern = rf"^remote\.{re.escape(remote_name)}\."
    try:
        result = concurrency_group.run_process_to_completion(
            ["git", "config", "--get-regexp", pattern],
            cwd=source_repo_path,
            is_checked_after=True,
        )
    except ProcessError as e:
        raise CloneError(f"Failed to read remote config for {remote_name} from source") from e

    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        key, _, value = line.partition(" ")
        _run_git_command(
            ["git", "config", "--add", key, value],
            cwd=destination,
            concurrency_group=concurrency_group,
            error_message=f"Failed to replay config key {key} onto clone",
        )


def _set_fallback_origin(
    destination: Path,
    source_repo_path: Path,
    concurrency_group: ConcurrencyGroup,
) -> None:
    """Create a single ``origin`` remote pointing at the source path on disk.

    Used when the source repository has zero remotes. A standard fetch
    refspec is configured so that ``git checkout <branch>`` can DWIM to
    ``refs/remotes/origin/<branch>`` — without it, git refuses to create a
    local branch from a remote-tracking ref.
    """
    _run_git_command(
        ["git", "config", "remote.origin.url", str(source_repo_path)],
        cwd=destination,
        concurrency_group=concurrency_group,
        error_message="Failed to set fallback origin URL",
    )
    _run_git_command(
        ["git", "config", "--add", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*"],
        cwd=destination,
        concurrency_group=concurrency_group,
        error_message="Failed to set fallback origin fetch refspec",
    )


def _copy_remote_refs(
    source_repo_path: Path,
    destination: Path,
    concurrency_group: ConcurrencyGroup,
) -> None:
    """Copy all ``refs/remotes/*`` tracking refs from the source repo into the clone.

    Since the clone uses ``--reference`` to share the object store, the objects
    are already available — only the ref pointers need to be created. This is
    done via a single shell pipeline: ``git for-each-ref`` in the source piped
    into ``git update-ref --stdin`` in the clone.
    """
    src = shlex.quote(str(source_repo_path))
    dst = shlex.quote(str(destination))
    script = f"git -C {src} for-each-ref --format='create %(refname) %(objectname)' refs/remotes/ | git -C {dst} update-ref --stdin"
    command = ["bash", "-c", script]
    try:
        concurrency_group.run_process_to_completion(command, is_checked_after=True)
    except ProcessError:
        # Source repo may have no remote-tracking refs — not an error.
        logger.debug("No remote-tracking refs to copy from {} to {}", source_repo_path, destination)


def _copy_local_branches_as_origin_refs(
    source_repo_path: Path,
    destination: Path,
    concurrency_group: ConcurrencyGroup,
) -> None:
    """Project source's ``refs/heads/*`` onto the clone's ``refs/remotes/origin/*``.

    Used in the fallback case when the source repository has no remotes:
    the widened :func:`_copy_remote_refs` would copy nothing, but the clone
    still needs ``refs/remotes/origin/<branch>`` populated for
    merge-base / diff against ``origin/<branch>`` to work.
    """
    src = shlex.quote(str(source_repo_path))
    dst = shlex.quote(str(destination))
    script = f"git -C {src} for-each-ref --format='create refs/remotes/origin/%(refname:lstrip=2) %(objectname)' refs/heads/ | git -C {dst} update-ref --stdin"
    command = ["bash", "-c", script]
    try:
        concurrency_group.run_process_to_completion(command, is_checked_after=True)
    except ProcessError:
        # Source repo may have no local branches — not an error.
        logger.debug("No local branches to project as origin refs from {} to {}", source_repo_path, destination)


def _ensure_target_branch_resolvable_in_clone(
    source_repo_path: Path,
    destination: Path,
    target_branch: str,
    concurrency_group: ConcurrencyGroup,
) -> None:
    """Project source's ``refs/heads/<target_branch>`` into the clone if the
    branch exists in source as a local ref but the clone has no local ref for
    it.

    ``clone_repository`` deliberately mirrors source's *remote* layout and does
    not bulk-copy source's ``refs/heads/*`` (those are user-private working
    state and would clutter every workspace). The requested target branch is
    the one exception: a local-only branch in the source — e.g. a
    ``sculptor/transfer/*`` branch produced by the ``split-changes`` flow,
    which lands in the user's primary repo via
    ``git push local HEAD:sculptor/transfer/...`` and never reaches a real
    remote — must still be cloneable. Without this, the upcoming
    ``git checkout <branch>`` would fail with
    ``pathspec '<branch>' did not match any file(s) known to git`` because the
    auto-created refs that ``git clone`` projected from source's local
    branches were stripped by :func:`_remove_all_remotes`.
    """
    if _ref_exists(destination, f"refs/heads/{target_branch}", concurrency_group):
        return
    source_hash = _resolve_ref(source_repo_path, f"refs/heads/{target_branch}", concurrency_group)
    if source_hash is None:
        # Source has no local ref either — let the upcoming checkout fail with
        # its original "pathspec did not match" error so the surface stays
        # consistent for genuinely-missing branches.
        return
    _run_git_command(
        ["git", "update-ref", f"refs/heads/{target_branch}", source_hash],
        cwd=destination,
        concurrency_group=concurrency_group,
        error_message=f"Failed to project source's local branch {target_branch} into the clone",
    )


def _ref_exists(repo_path: Path, ref: str, concurrency_group: ConcurrencyGroup) -> bool:
    """Whether ``ref`` (e.g. ``refs/heads/foo``) resolves in ``repo_path``."""
    try:
        concurrency_group.run_process_to_completion(
            ["git", "rev-parse", "--verify", "--quiet", ref],
            cwd=repo_path,
            is_checked_after=True,
        )
        return True
    except ProcessError:
        return False


def _resolve_ref(repo_path: Path, ref: str, concurrency_group: ConcurrencyGroup) -> str | None:
    """Resolve ``ref`` to a commit hash in ``repo_path``, or ``None`` if it doesn't exist."""
    try:
        result = concurrency_group.run_process_to_completion(
            ["git", "rev-parse", "--verify", ref],
            cwd=repo_path,
            is_checked_after=True,
        )
    except ProcessError:
        return None
    return result.stdout.strip() or None


def _mirror_branch_upstream(
    source_repo_path: Path,
    destination: Path,
    branch: str,
    concurrency_group: ConcurrencyGroup,
) -> None:
    """If the source branch has an upstream, set the same upstream on the clone.

    If the source branch has no upstream, do nothing — the clone's branch
    will have no upstream either, mirroring the source.
    """
    try:
        result = concurrency_group.run_process_to_completion(
            ["git", "rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}"],
            cwd=source_repo_path,
            is_checked_after=True,
        )
    except ProcessError:
        return
    upstream = result.stdout.strip()
    if not upstream:
        return
    _run_git_command(
        ["git", "branch", f"--set-upstream-to={upstream}"],
        cwd=destination,
        concurrency_group=concurrency_group,
        error_message=f"Failed to set upstream {upstream} on branch {branch}",
    )


def _run_git_command(
    command: list[str],
    cwd: Path | None,
    concurrency_group: ConcurrencyGroup,
    error_message: str,
) -> None:
    """Run a git command and handle errors.

    Args:
        command: The git command and arguments to run.
        cwd: Working directory for the command, or None for current directory.
        concurrency_group: Concurrency group for process management.
        error_message: Message to include in the CloneError if the command fails.

    Raises:
        CloneError: If the command fails.
    """
    logger.debug("Running git command: {}", " ".join(command))
    try:
        concurrency_group.run_process_to_completion(
            command,
            cwd=cwd,
            is_checked_after=True,
        )
    except ProcessError as e:
        stderr = e.stderr.strip() if e.stderr else "No error output"
        logger.error("{}: {}", error_message, stderr)
        raise CloneError(f"{error_message}: {stderr}") from e
