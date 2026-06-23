import datetime
from contextlib import contextmanager
from pathlib import Path
from queue import Queue
from typing import Generator

from loguru import logger

from sculptor.database.models import Workspace
from sculptor.foundation.async_monkey_patches import log_exception
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.constants import ExceptionPriority
from sculptor.foundation.errors import ExpectedError
from sculptor.foundation.itertools import generate_flattened
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import WorkspaceID
from sculptor.primitives.threads import StopGapBackgroundPollingStreamSource
from sculptor.primitives.threads import StopPolling
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.data_model_service.api import CompletedTransaction
from sculptor.services.git_repo_service.api import ReadOnlyGitRepo
from sculptor.services.git_repo_service.default_implementation import LocalReadOnlyGitRepo
from sculptor.services.git_repo_service.error_types import GitRepoError
from sculptor.services.git_repo_service.error_types import GitRepoNotFoundError
from sculptor.web.data_types import StreamingUpdateSourceTypes
from sculptor.web.derived import WorkspaceBranchInfo
from sculptor.web.derived import WorkspaceTargetBranchesInfo


def _is_missing_repo_error(exc: BaseException) -> bool:
    """Whether a git failure means the workspace repo is gone for good.

    A torn-down workspace presents one of two ways (see SCU-1429):
    - its working directory was removed entirely, which the git service surfaces
      as a ``GitRepoNotFoundError`` (the repo path no longer exists);
    - the directory survives but is no longer a git repo — e.g. a worktree whose
      gitdir was pruned — which makes git print ``fatal: not a git repository``.

    Both are permanent from this backend's perspective: a workspace's working
    directory is stable for its lifetime, so once its repo vanishes the poller
    will never succeed again and should stop rather than retry forever.
    """
    # NOTE: GitRepoNotFoundError is a GitRepoError subclass, so it must be
    # checked first (it carries no stderr, so the stderr branch below misses it).
    if isinstance(exc, GitRepoNotFoundError):
        return True
    if isinstance(exc, GitRepoError):
        stderr = exc.stderr
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        return stderr is not None and "not a git repository" in stderr
    return False


def _get_branch_unless_repo_missing(repo: ReadOnlyGitRepo) -> str | None:
    try:
        return repo.get_current_git_branch()
    except GitRepoNotFoundError as e:
        raise StopPolling(f"workspace repo is gone (working dir missing): {e}") from e
    except GitRepoError as e:
        if _is_missing_repo_error(e):
            raise StopPolling(f"workspace repo is gone (not a git repository): {e}") from e
        if e.branch_name is not None:
            raise
        logger.debug("There is no current branch: {}", e)
        return None


_WORKSPACE_BRANCH_POLL_SECONDS = 3.0
_WORKSPACE_TARGET_BRANCHES_POLL_SECONDS = 3.0


class _WorkspaceBranchPollingManager:
    """Polls the current branch and remote-tracking branches for each active workspace.

    Filter precedence: workspace_filter > project_filter > none. When
    workspace_filter is set, project_filter is ignored.
    """

    def __init__(
        self,
        services: CompleteServiceCollection,
        queue: Queue[StreamingUpdateSourceTypes],
        concurrency_group: ConcurrencyGroup,
        workspace_filter: WorkspaceID | None = None,
        project_filter: ProjectID | None = None,
    ):
        self._services = services
        self._queue = queue
        self._concurrency_group = concurrency_group
        self._workspace_filter = workspace_filter
        self._project_filter = None if workspace_filter is not None else project_filter
        self._sources_by_workspace_id: dict[WorkspaceID, StopGapBackgroundPollingStreamSource] = {}
        self._target_branches_sources_by_workspace_id: dict[WorkspaceID, StopGapBackgroundPollingStreamSource] = {}
        # Tracks the working dir each poller was started against, so we can
        # avoid restarting the polling thread on unrelated workspace updates
        # (e.g. diff_status transitions). Restarting on every upsert resets
        # the per-callback `_last_branch` baseline and would prevent the
        # branch-change detection from ever seeing two different values.
        self._working_dirs_by_workspace_id: dict[WorkspaceID, Path] = {}

    def _is_workspace_in_scope(self, workspace: Workspace) -> bool:
        if self._workspace_filter is not None:
            return workspace.object_id == self._workspace_filter
        if self._project_filter is not None:
            return workspace.project_id == self._project_filter
        return True

    def initialize(self) -> None:
        with self._services.data_model_service.open_transaction(RequestID()) as transaction:
            workspaces = transaction.get_workspaces()
        for workspace in workspaces:
            if workspace.is_deleted:
                continue
            if not self._is_workspace_in_scope(workspace):
                continue
            self._try_start_polling_for_workspace(workspace)

    def update_pollers_based_on_stream(self, models: list[StreamingUpdateSourceTypes]) -> None:
        updated_models = (m.updated_models for m in models if isinstance(m, CompletedTransaction))
        for updated_model in generate_flattened(updated_models):
            if isinstance(updated_model, Workspace):
                if not self._is_workspace_in_scope(updated_model):
                    continue
                if updated_model.is_deleted:
                    self._stop_polling_for_workspace(updated_model.object_id)
                    continue
                new_working_dir = _resolve_workspace_working_dir(self._services, updated_model)
                existing_working_dir = self._working_dirs_by_workspace_id.get(updated_model.object_id)
                if new_working_dir == existing_working_dir:
                    # Working dir unchanged — keep the existing polling thread
                    # (and its `_last_branch` baseline) running.
                    continue
                # Working dir changed (e.g. environment_id was just set, or
                # the environment was recreated): tear down and restart.
                self._stop_polling_for_workspace(updated_model.object_id)
                if new_working_dir is not None:
                    self._try_start_polling_for_workspace(updated_model)

    def _try_start_polling_for_workspace(self, workspace: Workspace) -> None:
        if workspace.object_id in self._sources_by_workspace_id:
            return
        working_dir = _resolve_workspace_working_dir(self._services, workspace)
        if working_dir is None:
            return
        polling_callback = _WorkspaceBranchPollingCallback(
            workspace_id=workspace.object_id,
            workspace_working_dir=working_dir,
            concurrency_group=self._concurrency_group,
            services=self._services,
        )
        source: StopGapBackgroundPollingStreamSource = StopGapBackgroundPollingStreamSource(
            polling_callback=polling_callback,
            output_queue=self._queue,
            check_interval_in_seconds=_WORKSPACE_BRANCH_POLL_SECONDS,
            concurrency_group=self._concurrency_group,
        )
        source.start()
        self._sources_by_workspace_id[workspace.object_id] = source
        self._working_dirs_by_workspace_id[workspace.object_id] = working_dir

        target_branches_callback = _WorkspaceTargetBranchesPollingCallback(
            workspace_id=workspace.object_id,
            workspace_working_dir=working_dir,
            concurrency_group=self._concurrency_group,
        )
        target_branches_source: StopGapBackgroundPollingStreamSource = StopGapBackgroundPollingStreamSource(
            polling_callback=target_branches_callback,
            output_queue=self._queue,
            check_interval_in_seconds=_WORKSPACE_TARGET_BRANCHES_POLL_SECONDS,
            concurrency_group=self._concurrency_group,
        )
        target_branches_source.start()
        self._target_branches_sources_by_workspace_id[workspace.object_id] = target_branches_source

    def _stop_polling_for_workspace(self, workspace_id: WorkspaceID) -> None:
        source = self._sources_by_workspace_id.pop(workspace_id, None)
        if source is not None:
            source.stop()
        target_branches_source = self._target_branches_sources_by_workspace_id.pop(workspace_id, None)
        if target_branches_source is not None:
            target_branches_source.stop()
        self._working_dirs_by_workspace_id.pop(workspace_id, None)

    def shutdown(self) -> None:
        for workspace_id in list(self._sources_by_workspace_id.keys()):
            self._stop_polling_for_workspace(workspace_id)


@contextmanager
def manage_workspace_branch_polling(
    services: CompleteServiceCollection,
    queue: Queue[StreamingUpdateSourceTypes],
    concurrency_group: ConcurrencyGroup,
    workspace_filter: WorkspaceID | None = None,
    project_filter: ProjectID | None = None,
) -> Generator[_WorkspaceBranchPollingManager, None, None]:
    manager = _WorkspaceBranchPollingManager(
        services=services,
        queue=queue,
        concurrency_group=concurrency_group,
        workspace_filter=workspace_filter,
        project_filter=project_filter,
    )
    try:
        yield manager
    finally:
        manager.shutdown()


class _WorkspaceBranchPollingCallback:
    """Polls the current git branch for a workspace's working directory."""

    def __init__(
        self,
        workspace_id: WorkspaceID,
        workspace_working_dir: Path,
        concurrency_group: ConcurrencyGroup,
        services: CompleteServiceCollection,
    ):
        self._workspace_id = workspace_id
        self._workspace_working_dir = workspace_working_dir
        self._concurrency_group = concurrency_group
        self._services = services
        self._first_failure_since_last_success: tuple[datetime.datetime, Exception] | None = None
        self._last_branch: str | None = None

    def __call__(self) -> WorkspaceBranchInfo | None:
        try:
            repo = LocalReadOnlyGitRepo(
                repo_path=self._workspace_working_dir,
                concurrency_group=self._concurrency_group,
                log_command=False,
            )
            current_branch = _get_branch_unless_repo_missing(repo)
            if current_branch is None:
                return None
            # External git operations (e.g. `git checkout` from the terminal)
            # don't fire on_diff_needed; regenerate the diff artifact here so
            # the frontend gets a fresh diff over its normal WS-driven
            # invalidation path. We use `maybe_refresh_workspace_diff` (which
            # rewrites the artifact file) rather than `mark_workspace_diff_stale`
            # (which only updates the timestamp): a stale on-disk artifact from
            # the previous branch would otherwise be returned to the next
            # `GET /workspaces/{id}/diff` request without `force_refresh=true`.
            if self._last_branch is not None and self._last_branch != current_branch:
                try:
                    self._services.workspace_service.maybe_refresh_workspace_diff(self._workspace_id)
                except ExpectedError as e:
                    # Expected/transient failures: git lock contention, workspace
                    # deleted between detection and refresh, process timeout.
                    # The user sees a stale diff until the next branch change or
                    # an agent-initiated refresh, so log at warning rather than
                    # debug.
                    logger.warning("Failed to refresh workspace diff on branch change: {}", e)
            self._last_branch = current_branch
            self._first_failure_since_last_success = None
            return WorkspaceBranchInfo(
                current_branch=current_branch,
                workspace_id=self._workspace_id,
            )
        except StopPolling:
            # The repo is gone for good; let the polling source stop us rather
            # than swallowing this into the generic failure path below.
            raise
        except Exception as e:
            if self._first_failure_since_last_success is None:
                self._first_failure_since_last_success = (datetime.datetime.now(), e)
                log_exception(e, message="Failed to get workspace branch", priority=ExceptionPriority.LOW_PRIORITY)
                return None
            original_time, original_exc = self._first_failure_since_last_success
            msg = "Still failing to get workspace branch: {} (original was {} @ {})"
            logger.info(msg, e, type(original_exc), original_time.isoformat())
            return None


class _WorkspaceTargetBranchesPollingCallback:
    """Polls the branches a workspace can target as its merge/diff base.

    These are the repo's remote-tracking branches, or — when the repo has no
    remote — its local branches, so the selector can still offer merge targets
    on a repo with no remote.
    """

    def __init__(
        self,
        workspace_id: WorkspaceID,
        workspace_working_dir: Path,
        concurrency_group: ConcurrencyGroup,
    ):
        self._workspace_id = workspace_id
        self._workspace_working_dir = workspace_working_dir
        self._concurrency_group = concurrency_group
        self._first_failure_since_last_success: tuple[datetime.datetime, Exception] | None = None

    def __call__(self) -> WorkspaceTargetBranchesInfo | None:
        try:
            repo = LocalReadOnlyGitRepo(
                repo_path=self._workspace_working_dir,
                concurrency_group=self._concurrency_group,
                log_command=False,
            )
            branches = repo.get_remote_branches()
            if not branches:
                # A repo with no remote (e.g. a local-only project) has no
                # remote-tracking branches, which would leave the target-branch
                # selector empty and the merge target stuck. Fall back to the
                # repo's local branches so the user can still pick a target,
                # excluding the workspace's own branch (diffing a branch against
                # itself is a no-op).
                current_branch = repo.get_current_git_branch()
                branches = [branch for branch in repo.get_all_branches() if branch != current_branch]
            self._first_failure_since_last_success = None
            return WorkspaceTargetBranchesInfo(
                workspace_id=self._workspace_id,
                target_branches=tuple(branches),
            )
        except Exception as e:
            if _is_missing_repo_error(e):
                # The repo is gone for good; stop polling rather than retrying
                # (and logging) every cycle until process shutdown (SCU-1429).
                raise StopPolling(f"workspace repo is gone: {e}") from e
            if self._first_failure_since_last_success is None:
                self._first_failure_since_last_success = (datetime.datetime.now(), e)
                log_exception(
                    e, message="Failed to list workspace target branches", priority=ExceptionPriority.LOW_PRIORITY
                )
                return None
            original_time, original_exc = self._first_failure_since_last_success
            logger.info(
                "Still failing to list workspace target branches: {} (original was {} @ {})",
                e,
                type(original_exc),
                original_time.isoformat(),
            )
            return None


def _resolve_workspace_working_dir(services: CompleteServiceCollection, workspace: Workspace) -> Path | None:
    """Resolve the git working directory for a workspace.

    Delegates to WorkspaceService.get_workspace_working_directory so that the
    IN_PLACE vs CLONE path resolution lives in the Environment abstraction.

    Returns None if the workspace environment hasn't been initialized yet.
    """
    return services.workspace_service.get_workspace_working_directory(workspace)
