"""Per-workspace jj state detection, owned by ``WorkspaceService``, beside the branch poller.

This watches each live jj workspace and fans two signals out to subscriber queues:

- the workspace's **jj state**: its working copy and the bookmarks on its
  stack. A changed working-copy change id, which a commit or ``jj new`` makes,
  also regenerates the workspace's diff; and
- the workspace's **target branches**: the repository's unconflicted
  bookmarks, minus the workspace's own.

Workspaces are grouped by the repository store they share. A cycle lists the
store's ``op_heads/heads``, whose file names change on every jj operation, so
an idle repository costs no process; a changed one is read with two commands
however many workspaces it has. A periodic forced re-read covers what no
operation records, such as a change to the user's jj config.

The poller never snapshots, so it never finds a working copy stale itself:
the workspace service marks one in the stale working-copy registry when a
snapshot fails that way, and every cycle publishes the mark.

While jj is unavailable a cycle does nothing at all. The poller does not
check jj itself: it reads the readiness the dependency service last
published.
"""

import threading
from collections.abc import Sequence
from pathlib import Path
from queue import Empty
from queue import Queue
from typing import Callable
from typing import assert_never

from loguru import logger

from sculptor.database.models import Workspace
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.foundation.async_monkey_patches import log_exception
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.constants import ExceptionPriority
from sculptor.foundation.errors import ExpectedError
from sculptor.primitives.ids import WorkspaceID
from sculptor.services.workspace_service.stale_working_copy_registry import StaleWorkingCopyRegistry
from sculptor.services.workspace_service.vcs.errors import GitCommandInJjWorkspaceError
from sculptor.services.workspace_service.vcs.jj_cli import JjCli
from sculptor.services.workspace_service.vcs.jj_data_types import JjHeadIdentity
from sculptor.services.workspace_service.vcs.jj_repo_queries import select_target_candidates
from sculptor.services.workspace_service.vcs.jj_workspace_scan import JjRepositoryScan
from sculptor.services.workspace_service.vcs.jj_workspace_scan import name_pull_request_base
from sculptor.services.workspace_service.vcs.jj_workspace_scan import project_jj_workspace_identity
from sculptor.services.workspace_service.vcs.jj_workspace_scan import scan_jj_workspaces
from sculptor.web.data_types import DependenciesStatus
from sculptor.web.data_types import JjReadiness
from sculptor.web.data_types import StreamingUpdateSourceTypes
from sculptor.web.data_types import WorkspaceJjStateInfo
from sculptor.web.data_types import WorkspaceTargetBranchesInfo

# The branch poller's interval, so a jj workspace's header follows the agent as quickly as a git one's.
_JJ_POLL_INTERVAL_IN_SECONDS = 3.0
_FALLBACK_RECOMPUTE_EVERY_CYCLES = 20
_STORE_LINK = Path(".jj") / "repo"
_OPERATION_HEADS = Path("op_heads") / "heads"

# What a repository was last read for: its operation heads, and each workspace's name and target.
_RepositoryScanKey = tuple[frozenset[str], frozenset[tuple[str, str | None]]]


class PublishedJjReadiness:
    """The jj readiness the dependency service last published, read without running jj.

    ``updates`` is registered as an observer of the dependency service, which
    pushes its whole status every time it computes one: on each health check
    from an open window, and around installs and settings changes.
    """

    def __init__(self) -> None:
        self.updates: Queue[DependenciesStatus] = Queue()
        self._latest: JjReadiness | None = None

    def read_latest(self) -> JjReadiness | None:
        """The most recently published readiness; None until the first status arrives."""
        while True:
            try:
                status = self.updates.get_nowait()
            except Empty:
                return self._latest
            self._latest = status.jj_readiness


class JjWorkspacePoller:
    """Owns the jj scan loop and the subscriber fan-out for jj workspace state."""

    def __init__(
        self,
        *,
        concurrency_group: ConcurrencyGroup,
        read_workspaces: Callable[[], Sequence[Workspace]],
        jj: JjCli,
        resolve_working_dir: Callable[[Workspace], Path | None],
        refresh_diff_on_working_copy_change: Callable[[WorkspaceID], None],
        stale_working_copies: StaleWorkingCopyRegistry,
        read_jj_readiness: Callable[[], JjReadiness | None],
    ) -> None:
        self._concurrency_group = concurrency_group
        self._read_workspaces = read_workspaces
        self._jj = jj
        self._resolve_working_dir = resolve_working_dir
        self._refresh_diff_on_working_copy_change = refresh_diff_on_working_copy_change
        self._stale_working_copies = stale_working_copies
        self._read_jj_readiness = read_jj_readiness

        self._stop_event = threading.Event()

        # ``_observer_lock`` guards the observer list and the two last-emitted caches,
        # which a backfill in add_observer and a read in get_jj_state iterate while
        # the scan thread writes them.
        self._observers: list[Queue[StreamingUpdateSourceTypes]] = []
        self._observer_lock = threading.Lock()
        self._state_by_workspace: dict[WorkspaceID, WorkspaceJjStateInfo] = {}
        self._target_info_by_workspace: dict[WorkspaceID, WorkspaceTargetBranchesInfo] = {}

        # Scan-thread-only, so they need no lock.
        self._scan_by_store: dict[Path, JjRepositoryScan] = {}
        self._scan_key_by_store: dict[Path, _RepositoryScanKey] = {}
        # Workspaces and stores whose last scan failed, so a lasting failure is logged once.
        self._failed_scan_keys: set[WorkspaceID | Path] = set()

        self._cycle = 0

    # -- Observer registry -------------------------------------------------

    def add_observer(self, queue: Queue[StreamingUpdateSourceTypes]) -> None:
        """Register a subscriber queue and immediately backfill current state.

        Per-connection scope filtering is the caller's job: ``project_for_scope``
        in ``streams.py`` drops out-of-scope entries from each ``StreamingUpdate``.
        """
        with self._observer_lock:
            self._observers.append(queue)
            for state in self._state_by_workspace.values():
                queue.put(state)
            for target_info in self._target_info_by_workspace.values():
                queue.put(target_info)

    def remove_observer(self, queue: Queue[StreamingUpdateSourceTypes]) -> None:
        with self._observer_lock:
            self._observers = [observer for observer in self._observers if observer is not queue]

    def get_jj_state(self, workspace_id: WorkspaceID) -> WorkspaceJjStateInfo | None:
        """The last-published state of a jj workspace; None if it has not been scanned or is no jj workspace."""
        with self._observer_lock:
            return self._state_by_workspace.get(workspace_id)

    def _publish(self, info: WorkspaceJjStateInfo | WorkspaceTargetBranchesInfo) -> None:
        with self._observer_lock:
            match info:
                case WorkspaceJjStateInfo():
                    self._state_by_workspace[info.workspace_id] = info
                case WorkspaceTargetBranchesInfo():
                    self._target_info_by_workspace[info.workspace_id] = info
                case _ as unreachable:
                    assert_never(unreachable)
            for observer in self._observers:
                observer.put(info)

    # -- Lifecycle ---------------------------------------------------------

    def start(self) -> None:
        self._concurrency_group.start_new_thread(
            target=self._run_loop,
            name="jj-workspace-scan",
            # A repository can be deleted mid-scan; the loop logs and continues rather
            # than failing the concurrency group.
            is_checked=False,
        )
        logger.debug("jj workspace poller started")

    def stop(self) -> None:
        self._stop_event.set()

    def _run_loop(self) -> None:
        while not self._stop_event.wait(_JJ_POLL_INTERVAL_IN_SECONDS):
            try:
                self._scan_once()
            except Exception as e:
                log_exception(e, "jj workspace scan cycle failed", priority=ExceptionPriority.LOW_PRIORITY)

    # -- Scan --------------------------------------------------------------

    def _scan_once(self) -> None:
        # Until the dependency service publishes a readiness, the poller scans as usual.
        readiness = self._read_jj_readiness()
        if readiness is not None and readiness.blocker is not None:
            return
        self._cycle += 1
        force_recompute = self._cycle % _FALLBACK_RECOMPUTE_EVERY_CYCLES == 0

        jj_workspaces = [
            workspace
            for workspace in self._read_workspaces()
            if not workspace.is_deleted and _is_jj_workspace(workspace.initialization_strategy)
        ]

        members_by_store = self._group_by_store(jj_workspaces)
        kept_workspace_ids: set[WorkspaceID] = set()
        for store, members in members_by_store.items():
            try:
                scan = self._read_repository(store, members, force_recompute)
            except Exception as e:
                self._log_scan_failure_once(store, e)
                # Their last state stays published until the repository can be read again.
                kept_workspace_ids.update(workspace.object_id for workspace, _ in members)
                continue
            self._failed_scan_keys.discard(store)
            for workspace, _ in members:
                try:
                    is_in_scan = self._update_workspace(workspace, scan)
                except Exception as e:
                    self._log_scan_failure_once(workspace.object_id, e)
                    kept_workspace_ids.add(workspace.object_id)
                    continue
                self._failed_scan_keys.discard(workspace.object_id)
                if is_in_scan:
                    kept_workspace_ids.add(workspace.object_id)

        self._prune(kept_workspace_ids, set(members_by_store))
        self._failed_scan_keys &= {workspace.object_id for workspace in jj_workspaces} | set(members_by_store)

    def _group_by_store(self, jj_workspaces: list[Workspace]) -> dict[Path, list[tuple[Workspace, Path]]]:
        """Each repository store with the workspaces, and their checkouts, that share it.

        A workspace whose checkout is not yet created, or no longer exists, is left out.
        """
        members_by_store: dict[Path, list[tuple[Workspace, Path]]] = {}
        for workspace in jj_workspaces:
            try:
                checkout = self._resolve_working_dir(workspace)
            except Exception as e:
                self._log_scan_failure_once(workspace.object_id, e)
                continue
            store = None if checkout is None else _find_repository_store(checkout)
            if checkout is None or store is None:
                self._failed_scan_keys.discard(workspace.object_id)
                continue
            members_by_store.setdefault(store, []).append((workspace, checkout))
        return members_by_store

    def _read_repository(
        self, store: Path, members: list[tuple[Workspace, Path]], force_recompute: bool
    ) -> JjRepositoryScan:
        """The repository's scan, read again only when an operation, a member or a member's target has changed."""
        operation_heads = frozenset(path.name for path in (store / _OPERATION_HEADS).iterdir())
        target_ref_by_workspace = {str(workspace.object_id): workspace.target_branch for workspace, _ in members}
        scan_key = (operation_heads, frozenset(target_ref_by_workspace.items()))
        cached_scan = self._scan_by_store.get(store)
        if cached_scan is not None and not force_recompute and self._scan_key_by_store.get(store) == scan_key:
            return cached_scan

        _, representative_checkout = members[0]
        scan = scan_jj_workspaces(self._jj, representative_checkout, target_ref_by_workspace)
        self._scan_by_store[store] = scan
        self._scan_key_by_store[store] = scan_key
        return scan

    def _update_workspace(self, workspace: Workspace, scan: JjRepositoryScan) -> bool:
        """Publish what changed in the workspace's state and targets; whether the scan found its working copy."""
        workspace_id = workspace.object_id
        identity = project_jj_workspace_identity(
            scan, str(workspace_id), workspace.target_branch, workspace.requested_branch_name
        )
        if identity is None:
            return False

        state = _to_state_info(workspace_id, identity, self._stale_working_copies.is_stale(workspace_id))
        previous_state = self._state_by_workspace.get(workspace_id)
        if state != previous_state:
            # Only a new working-copy change, not first detection, calls for a fresh
            # diff: a commit made outside Sculptor does not otherwise regenerate it.
            if previous_state is not None and previous_state.working_copy_change_id != state.working_copy_change_id:
                self._refresh_diff_safely(workspace_id)
            self._publish(state)

        target_info = _to_target_branches_info(workspace, identity, scan)
        if target_info != self._target_info_by_workspace.get(workspace_id):
            self._publish(target_info)
        return True

    def _refresh_diff_safely(self, workspace_id: WorkspaceID) -> None:
        try:
            self._refresh_diff_on_working_copy_change(workspace_id)
        except GitCommandInJjWorkspaceError as e:
            log_exception(e, f"Refreshing the diff of jj workspace {workspace_id} ran git in it")
        except ExpectedError as e:
            # The user sees the previous diff until the next refresh.
            logger.debug("Failed to refresh the diff of workspace {} on a new working copy: {}", workspace_id, e)

    def _log_scan_failure_once(self, key: WorkspaceID | Path, error: Exception) -> None:
        """Log that a workspace or repository cannot be scanned when that starts, not on every cycle it lasts."""
        if key in self._failed_scan_keys:
            return
        self._failed_scan_keys.add(key)
        log_exception(
            error, f"jj workspace scan is skipping {key} until it can be read", priority=ExceptionPriority.LOW_PRIORITY
        )

    def _prune(self, kept_workspace_ids: set[WorkspaceID], live_stores: set[Path]) -> None:
        """Drop the state of workspaces that are gone, or whose working copy the repository no longer has."""
        with self._observer_lock:
            for workspace_id in set(self._state_by_workspace) - kept_workspace_ids:
                self._state_by_workspace.pop(workspace_id)
            for workspace_id in set(self._target_info_by_workspace) - kept_workspace_ids:
                self._target_info_by_workspace.pop(workspace_id)
        for store in set(self._scan_by_store) - live_stores:
            self._scan_by_store.pop(store)
            self._scan_key_by_store.pop(store, None)


def _is_jj_workspace(initialization_strategy: WorkspaceInitializationStrategy) -> bool:
    match initialization_strategy:
        case (
            WorkspaceInitializationStrategy.IN_PLACE
            | WorkspaceInitializationStrategy.CLONE
            | WorkspaceInitializationStrategy.WORKTREE
        ):
            return False
        case WorkspaceInitializationStrategy.JJ_WORKSPACE:
            return True
        case _ as unreachable:
            assert_never(unreachable)


def _find_repository_store(checkout: Path) -> Path | None:
    """The repository store a jj checkout links to; None when the checkout has no `.jj`.

    A workspace added with `jj workspace add` holds a file naming the store
    relative to its `.jj`; a repository's own first workspace holds the store itself.
    """
    store_link = checkout / _STORE_LINK
    try:
        return (store_link.parent / store_link.read_text()).resolve()
    except IsADirectoryError:
        return store_link.resolve()
    except (FileNotFoundError, NotADirectoryError):
        return None


def _to_state_info(workspace_id: WorkspaceID, identity: JjHeadIdentity, is_stale: bool) -> WorkspaceJjStateInfo:
    return WorkspaceJjStateInfo(
        workspace_id=workspace_id,
        working_copy_change_id=identity.working_copy_change_id,
        working_copy_change_id_prefix_length=len(identity.working_copy_change_id_prefix),
        working_copy_description=identity.description_first_line,
        is_working_copy_empty=identity.is_working_copy_empty,
        bookmarks=identity.bookmarks,
        primary_bookmark=identity.primary_bookmark,
        unbookmarked_revision_count=identity.unbookmarked_revision_count,
        has_conflict=identity.has_conflict,
        is_divergent=identity.is_divergent,
        is_working_copy_stale=is_stale,
    )


def _to_target_branches_info(
    workspace: Workspace, identity: JjHeadIdentity, scan: JjRepositoryScan
) -> WorkspaceTargetBranchesInfo:
    """The bookmarks the workspace may target, without its own: diffing a stack against itself shows nothing."""
    own_bookmarks = set(identity.bookmarks)
    target_branches = tuple(
        symbol for symbol in select_target_candidates(scan.bookmarks) if symbol not in own_bookmarks
    )
    named_refs = target_branches if workspace.target_branch is None else (*target_branches, workspace.target_branch)
    return WorkspaceTargetBranchesInfo(
        workspace_id=workspace.object_id,
        target_branches=target_branches,
        pr_base_names={ref: name_pull_request_base(ref) for ref in named_refs},
    )
