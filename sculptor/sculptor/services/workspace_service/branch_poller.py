"""Per-workspace git state detection, owned by ``WorkspaceService``.

This watches each live workspace's git state and fans two signals out to
subscriber queues:

- the **current branch** of the workspace's ``HEAD`` (genuinely workspace-scoped:
  every worktree has its own ``HEAD``), which also drives a side effect —
  regenerating the diff when the branch changes out from under us; and
- the workspace's **target branches** (the merge/diff candidates the selector
  offers), projected from the repo's remote-tracking branches, falling back to
  local branches minus the workspace's own when the repo has no remote.

Remote-tracking refs are a property of the *repo*, not the workspace, so they are
scanned once per **common git dir** and reused across every workspace sharing it.
This is the right key — not the project: an IN_PLACE workspace and the project's
worktrees share one common dir, but each CLONE-mode workspace is an independent
clone with its own ``refs/remotes``, so a ref freshly fetched into one clone is
invisible from any other repo (including the project's own). Keying on the common
dir scans each distinct repo exactly once and lets a clone see its own fetches.

Both scans are stat-first: a cycle stats the relevant ref files (``HEAD`` for the
branch; ``packed-refs`` + ``refs/remotes`` for the targets) and only reads/forks
``git`` when a signature actually moved, so an idle cycle forks nothing. A
periodic forced recompute covers ref-mutation shapes that leave the signature
unchanged (e.g. a loose ref being packed).

Results are fanned out as ``WorkspaceBranchInfo`` / ``WorkspaceTargetBranchesInfo``
— the same streaming types as before — so the downstream stream conversion and
PR-polling coupling are unchanged. A single loop serves the whole process;
websocket connections subscribe rather than each starting their own pollers.
"""

import threading
from pathlib import Path
from queue import Queue
from typing import Callable

from loguru import logger

from sculptor.database.models import Workspace
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.errors import ExpectedError
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import WorkspaceID
from sculptor.services.data_model_service.api import DataModelService
from sculptor.services.git_repo_service.default_implementation import LocalReadOnlyGitRepo
from sculptor.services.git_repo_service.error_types import GitRepoError
from sculptor.services.git_repo_service.error_types import GitRepoNotFoundError
from sculptor.services.git_repo_service.git_ref_scanning import RemoteRefsSignature
from sculptor.services.git_repo_service.git_ref_scanning import StatSignature
from sculptor.services.git_repo_service.git_ref_scanning import read_current_branch
from sculptor.services.git_repo_service.git_ref_scanning import remote_refs_signature
from sculptor.services.git_repo_service.git_ref_scanning import resolve_git_dirs
from sculptor.services.git_repo_service.git_ref_scanning import stat_signature
from sculptor.web.data_types import StreamingUpdateSourceTypes
from sculptor.web.data_types import WorkspaceBranchInfo
from sculptor.web.data_types import WorkspaceTargetBranchesInfo

# Matches the previous per-workspace poll interval so detection latency (and the
# e2e waits keyed to it) are unchanged.
_BRANCH_POLL_INTERVAL_IN_SECONDS = 3.0
# Periodic forced re-read even when the HEAD stat signature looks unchanged — the
# backstop for filesystems with coarse mtime granularity. ~20 cycles ≈ 60s.
_FALLBACK_RECOMPUTE_EVERY_CYCLES = 20


class WorkspaceBranchPoller:
    """Owns the branch scan loop and the subscriber fan-out for workspace git state."""

    def __init__(
        self,
        *,
        concurrency_group: ConcurrencyGroup,
        data_model_service: DataModelService,
        resolve_working_dir: Callable[[Workspace], Path | None],
        refresh_diff_on_branch_change: Callable[[WorkspaceID], None],
    ) -> None:
        self._concurrency_group = concurrency_group
        self._data_model_service = data_model_service
        self._resolve_working_dir = resolve_working_dir
        self._refresh_diff_on_branch_change = refresh_diff_on_branch_change

        self._stop_event = threading.Event()

        # Observer fan-out. ``_observer_lock`` guards BOTH the observer list and
        # the two last-emitted caches below, because a backfill in add_observer
        # iterates those caches while the scan thread may be writing them — taking
        # the lock for every write and every read serializes the two and prevents
        # "dictionary changed size during iteration".
        self._observers: list[Queue[StreamingUpdateSourceTypes]] = []
        self._observer_lock = threading.Lock()

        # Last-emitted state, also used to backfill newly-attached observers.
        # Read by add_observer under ``_observer_lock``; the scan thread therefore
        # writes them only via ``_publish_*`` / ``_prune`` under the same lock.
        self._branch_info_by_workspace: dict[WorkspaceID, WorkspaceBranchInfo] = {}
        self._target_info_by_workspace: dict[WorkspaceID, WorkspaceTargetBranchesInfo] = {}
        # Scan-thread-only (never read by add_observer), so it needs no lock.
        self._head_signature_by_workspace: dict[WorkspaceID, StatSignature | None] = {}

        # Repo-level merge-target candidates, keyed by common git dir and computed
        # once per repo per change. Touched only by the single scan thread, so no
        # lock — the backfill never reads these (it reads the per-workspace
        # projection in ``_target_info_by_workspace``).
        self._remote_signature_by_common_dir: dict[Path, RemoteRefsSignature] = {}
        self._remote_branches_by_common_dir: dict[Path, tuple[str, ...]] = {}
        self._local_branches_by_common_dir: dict[Path, tuple[str, ...]] = {}

        self._cycle = 0

    # -- Observer registry -------------------------------------------------

    def add_observer(self, queue: Queue[StreamingUpdateSourceTypes]) -> None:
        """Register a subscriber queue and immediately backfill current state.

        Per-connection scope filtering is the caller's job: ``project_for_scope``
        in ``streams.py`` drops out-of-scope entries from each ``StreamingUpdate``.
        """
        with self._observer_lock:
            self._observers.append(queue)
            for branch_info in self._branch_info_by_workspace.values():
                queue.put(branch_info)
            for target_info in self._target_info_by_workspace.values():
                queue.put(target_info)

    def remove_observer(self, queue: Queue[StreamingUpdateSourceTypes]) -> None:
        with self._observer_lock:
            self._observers = [observer for observer in self._observers if observer is not queue]

    def get_current_branch(self, workspace_id: WorkspaceID) -> str | None:
        """Return the last-scanned current branch for a workspace, or None if not yet scanned."""
        with self._observer_lock:
            info = self._branch_info_by_workspace.get(workspace_id)
        return info.current_branch if info is not None else None

    def _publish_branch_info(self, info: WorkspaceBranchInfo) -> None:
        """Atomically record and fan out a branch update under ``_observer_lock``."""
        with self._observer_lock:
            self._branch_info_by_workspace[info.workspace_id] = info
            for observer in self._observers:
                observer.put(info)

    def _publish_target_info(self, info: WorkspaceTargetBranchesInfo) -> None:
        """Atomically record and fan out a target-branches update under ``_observer_lock``."""
        with self._observer_lock:
            self._target_info_by_workspace[info.workspace_id] = info
            for observer in self._observers:
                observer.put(info)

    # -- Lifecycle ---------------------------------------------------------

    def start(self) -> None:
        self._concurrency_group.start_new_thread(
            target=self._run_loop,
            name="workspace-branch-scan",
            # The repo can be deleted mid-scan; the loop logs and continues rather
            # than failing the concurrency group.
            is_checked=False,
        )
        logger.debug("Workspace branch poller started")

    def stop(self) -> None:
        self._stop_event.set()

    def _run_loop(self) -> None:
        while not self._stop_event.wait(_BRANCH_POLL_INTERVAL_IN_SECONDS):
            try:
                self._scan_once()
            except Exception as e:
                logger.warning("Workspace branch scan cycle failed: {}", e)

    # -- Scan --------------------------------------------------------------

    def _scan_once(self) -> None:
        self._cycle += 1
        force_recompute = self._cycle % _FALLBACK_RECOMPUTE_EVERY_CYCLES == 0

        with self._data_model_service.open_transaction(RequestID()) as transaction:
            workspaces = list(transaction.get_workspaces())

        live_workspace_ids: set[WorkspaceID] = set()
        # Group live workspaces by the common git dir they share so the repo-level
        # remote scan runs once per repo, not once per workspace. ``working_dir``
        # is a representative checkout to fork git from for that repo.
        members_by_common_dir: dict[Path, list[Workspace]] = {}
        working_dir_by_common_dir: dict[Path, Path] = {}

        for workspace in workspaces:
            if workspace.is_deleted:
                continue
            working_dir = self._resolve_working_dir(workspace)
            if working_dir is None:
                continue
            git_dirs = resolve_git_dirs(working_dir)
            if git_dirs is None:
                continue
            git_dir, common_dir = git_dirs
            live_workspace_ids.add(workspace.object_id)
            # Branch first: the target projection's no-remote fallback excludes the
            # workspace's own (current) branch, so the branch cache must be current.
            self._update_branch(workspace, working_dir, git_dir, force_recompute)
            members_by_common_dir.setdefault(common_dir, []).append(workspace)
            working_dir_by_common_dir.setdefault(common_dir, working_dir)

        for common_dir, members in members_by_common_dir.items():
            self._scan_remote_branches(common_dir, working_dir_by_common_dir[common_dir], force_recompute)
            for workspace in members:
                self._update_target_branches(workspace, common_dir)

        self._prune(live_workspace_ids, set(members_by_common_dir))

    def _update_branch(self, workspace: Workspace, working_dir: Path, git_dir: Path, force_recompute: bool) -> None:
        workspace_id = workspace.object_id
        head_signature = stat_signature(git_dir / "HEAD")
        already_known = workspace_id in self._branch_info_by_workspace
        if (
            not force_recompute
            and already_known
            and head_signature is not None
            and self._head_signature_by_workspace.get(workspace_id) == head_signature
        ):
            return  # Fast path: HEAD unchanged since last scan — no read, no fork.

        current_branch = read_current_branch(working_dir, git_dir, self._concurrency_group)
        if current_branch is None:
            return  # No current branch yet (unborn HEAD) or repo transiently unreadable.

        self._head_signature_by_workspace[workspace_id] = head_signature
        previous = self._branch_info_by_workspace.get(workspace_id)
        if previous is not None and previous.current_branch == current_branch:
            return  # Value unchanged; nothing to emit.

        # Refresh the diff only on an actual branch transition, not first detection
        # — an external `git checkout` does not otherwise regenerate the artifact.
        if previous is not None and previous.current_branch != current_branch:
            self._refresh_diff_safely(workspace_id)
        self._publish_branch_info(WorkspaceBranchInfo(current_branch=current_branch, workspace_id=workspace_id))

    def _scan_remote_branches(self, common_dir: Path, working_dir: Path, force_recompute: bool) -> None:
        """Refresh the cached merge-target candidates for the repo at ``common_dir``.

        Stat-first: an unchanged remote-ref signature skips the git fork. Computed
        once per common dir per cycle and reused for every workspace on that repo.
        """
        signature = remote_refs_signature(common_dir)
        already_scanned = common_dir in self._remote_branches_by_common_dir
        unchanged = self._remote_signature_by_common_dir.get(common_dir) == signature
        if not force_recompute and already_scanned and unchanged:
            return  # Stat fast-path: remote refs unchanged since last scan — no fork.

        repo = LocalReadOnlyGitRepo(
            repo_path=working_dir, concurrency_group=self._concurrency_group, log_command=False
        )
        try:
            remote_branches = tuple(repo.get_remote_branches())
            # Only need local branches as the fallback when there is no remote.
            local_branches = () if remote_branches else tuple(repo.get_all_branches())
        except GitRepoNotFoundError:
            return  # Repo vanished mid-scan; a later cycle prunes it.
        except GitRepoError as e:
            logger.warning("Failed to list remote branches for {}: {}", common_dir, e)
            return

        self._remote_signature_by_common_dir[common_dir] = signature
        self._remote_branches_by_common_dir[common_dir] = remote_branches
        self._local_branches_by_common_dir[common_dir] = local_branches

    def _update_target_branches(self, workspace: Workspace, common_dir: Path) -> None:
        if common_dir not in self._remote_branches_by_common_dir:
            return  # Repo not scanned yet (transient git error); a later cycle emits.

        remote_branches = self._remote_branches_by_common_dir[common_dir]
        if remote_branches:
            target_branches = remote_branches
        else:
            current = self._branch_info_by_workspace.get(workspace.object_id)
            current_branch = current.current_branch if current is not None else None
            # Exclude the workspace's own branch — diffing a branch against itself
            # is a no-op.
            local_branches = self._local_branches_by_common_dir.get(common_dir, ())
            target_branches = tuple(branch for branch in local_branches if branch != current_branch)

        previous = self._target_info_by_workspace.get(workspace.object_id)
        if previous is not None and previous.target_branches == target_branches:
            return
        self._publish_target_info(
            WorkspaceTargetBranchesInfo(workspace_id=workspace.object_id, target_branches=target_branches)
        )

    def _refresh_diff_safely(self, workspace_id: WorkspaceID) -> None:
        try:
            self._refresh_diff_on_branch_change(workspace_id)
        except ExpectedError as e:
            # Expected/transient: git lock contention, workspace deleted between
            # detection and refresh, process timeout. The user sees a stale diff
            # until the next branch change or an agent-initiated refresh.
            logger.warning("Failed to refresh workspace diff on branch change: {}", e)

    def _prune(self, live_workspace_ids: set[WorkspaceID], live_common_dirs: set[Path]) -> None:
        stale_ids = (set(self._branch_info_by_workspace) | set(self._target_info_by_workspace)) - live_workspace_ids
        # Pop from the observer-visible caches under the lock (add_observer may be
        # iterating them); the head-signature cache is scan-thread-only.
        with self._observer_lock:
            for workspace_id in stale_ids:
                self._branch_info_by_workspace.pop(workspace_id, None)
                self._target_info_by_workspace.pop(workspace_id, None)
        for workspace_id in stale_ids:
            self._head_signature_by_workspace.pop(workspace_id, None)
        stale_common_dirs = set(self._remote_branches_by_common_dir) - live_common_dirs
        for common_dir in stale_common_dirs:
            self._remote_signature_by_common_dir.pop(common_dir, None)
            self._remote_branches_by_common_dir.pop(common_dir, None)
            self._local_branches_by_common_dir.pop(common_dir, None)
