import threading
import time
from abc import ABC
from enum import StrEnum
from functools import cached_property
from pathlib import Path
from typing import Any
from typing import Final
from typing import Generator
from typing import Literal

from loguru import logger
from pydantic import Field

from imbue_core.constants import ExceptionPriority
from imbue_core.pydantic_serialization import MutableModel
from imbue_core.subprocess_utils import ProcessError
from sculptor.interfaces.agents.v1.agent import LocalSyncNoticeOfPause
from sculptor.interfaces.agents.v1.agent import LocalSyncNoticeUnion
from sculptor.services.git_repo_service.default_implementation import LocalReadOnlyGitRepo
from sculptor.services.local_sync_service.data_types import NewNoticesInSyncHandlingError
from sculptor.services.local_sync_service.local_sync_errors import MutagenSyncError
from sculptor.services.local_sync_service.mutagen_utils import create_controlled_mutagen_sync
from sculptor.services.local_sync_service.mutagen_utils import get_all_sculptor_mutagen_session_names
from sculptor.services.local_sync_service.mutagen_utils import get_git_ignored_patterns_for_mutagen
from sculptor.services.local_sync_service.mutagen_utils import run_mutagen_cmd
from sculptor.services.local_sync_service.mutagen_utils import terminate_mutagen_session
from sculptor.services.local_sync_service.path_batch_scheduler import LocalSyncSubReconciler
from sculptor.services.local_sync_service.path_batch_scheduler import is_path_under_any
from sculptor.utils.jsonl_logs import log_exception
from sculptor.utils.read_write_lock import ReadWriteLock

# TODO: Unify with mutagen approach and/or git ignoring
_DEFAULT_FILETREE_EXCLUSIONS: Final = tuple(
    Path(subdir) for subdir in (".git/", "node_modules/", ".venv/", "build/", "dist/", ".claude/")
)

LOCAL_FILESYNC_TAG: Final = "local_filetree_sync"
LOCAL_GIT_STATE_GUARDIAN_TAG: Final = "local_git_state_guardian"


# TODO:  .gitignore support, but . Very annoying that neither mutagen nor watchman support it.
class MultiRootFiletreeSubPathReconciler(LocalSyncSubReconciler, ABC):
    """filter a handful of root paths, excluding the given relative subpaths from each.

    NOTE: later when we add SSH path support, we'll extend this to include AnyUrls,
    and just filter on the whole "absolute" URI

    This is multi-root because they feed into a single mutagen reconciler
    """

    @property
    def root_paths(self) -> tuple[Path, ...]:
        raise NotImplementedError("This should be overridden in subclasses")

    excluded_relative_subpaths: tuple[Path, ...] = _DEFAULT_FILETREE_EXCLUSIONS

    def model_post_init(self, context: Any) -> None:
        super().model_post_init(context)
        for root_path in self.root_paths:
            assert root_path.is_absolute(), f"{root_path=} must be absolute"
        for subpath in self.excluded_relative_subpaths:
            assert not subpath.is_absolute(), (
                f"{subpath=} must be relative so it can be resolved against all root_paths in ({self})"
            )
        assert len(self.excluded_absolute_paths) > 0, (
            "Must have at least one excluded subpath - otherwise what's the point"
        )

    @property
    def dirs_to_watch(self) -> tuple[Path, ...]:
        return self.root_paths

    @cached_property
    def excluded_absolute_paths(self) -> tuple[Path, ...]:
        return tuple(root / subpath for subpath in self.excluded_relative_subpaths for root in self.root_paths)

    def is_relevant_subpath(self, path: Path) -> bool:
        """Check if the path is relevant by ensuring it is not under any excluded subpaths."""
        # path = path.resolve()
        # idk if this is fired all the time like I think it is, but if not I think it should always accompany nested events
        is_root_dir_event_that_should_be_ignored = path in self.root_paths
        if is_root_dir_event_that_should_be_ignored:
            logger.trace("Ignoring root directory event in reconciler {}: {}", self.tag, path)
            return False
        if not is_path_under_any(path, self.root_paths):
            return False
        return not is_path_under_any(path, self.excluded_absolute_paths)


class MutagenSyncStep(StrEnum):
    OVERWRITE_LOCAL_WITH_REMOTE = "OVERWRITE_LOCAL_WITH_REMOTE"
    # BIDIRECTIONAL_SAFE = "BIDIRECTIONAL_SAFE"

    # NOTE: We want to switch to BIDIRECTIONAL_SAFE as soon as is practical, but we need to actually implement the following:
    # 1. Observing conflicts: https://linear.app/imbue/issue/PROD-881/pause-monitor-mutagen-process-for-conflicts
    # 2. Surfacing conflicts: https://linear.app/imbue/issue/PROD-1402/local-sync-pause-state-ui-surface-causes-to-user
    # 3. Resolving conflicts https://linear.app/imbue/issue/PROD-2107/local-sync-mutagen-conflicts-resolution-ui
    BIDIRECTIONAL_USER_ALWAYS_WINS = "BIDIRECTIONAL_USER_ALWAYS_WINS"


_LastAction = Literal["create", "flush", "terminate"]


class MutagenSyncSession(MutableModel):
    name: str
    local: Path
    sync_step: MutagenSyncStep

    # This is an unusual URL-esque string used by Mutagen to synchronize directories over SSH.
    # It takes the form [<user>@]<host>[:<port>]:<path>.
    # See https://mutagen.io/documentation/transports/ssh/ for more information.
    remote_mutagen_url: str = Field(frozen=True)
    snapshot_guard: ReadWriteLock | None = None

    _last_attempted_action: _LastAction | None = None

    def model_post_init(self, context: Any) -> None:
        super().model_post_init(context)
        assert self.name.startswith("sculptor-"), f"all session names must have the 'sculptor-' prefix: {self}"

    @cached_property
    def remote_path(self) -> Path:
        return Path(self.remote_mutagen_url.split(":")[-1])

    @property
    def _mutagen_alpha_beta_and_mode(
        self,
    ) -> tuple[str, str, Literal["one-way-replica", "two-way-safe", "two-way-resolved"]]:
        """Mutagen mode resolve

        Mutagen Modes (abridged from https://mutagen.io/documentation/synchronization/#modes):
        two-way-safe:
            * both endpoints are treated with equal precedence.
            * conflicts are only automatically resolved if they don't result in data loss
            * If conflicts can't be automatically resolved, they are stored in the session state

        two-way-resolved: same as two-way-safe, but alpha automatically wins all conflicts, including deletions
        one-way-safe:
            * changes are only allowed to propagate from alpha to beta
            * extra content on beta that doesn't conflict with contents on alpha is simply ignored.
        one-way-replica: beta becomes an exact replica of alpha.
        """
        if self.sync_step == MutagenSyncStep.OVERWRITE_LOCAL_WITH_REMOTE:
            return (self.remote_mutagen_url, str(self.local), "one-way-replica")
        assert self.sync_step == MutagenSyncStep.BIDIRECTIONAL_USER_ALWAYS_WINS, f"Invalid sync step in {self}"
        return (str(self.local), self.remote_mutagen_url, "two-way-resolved")

    @property
    def _ignore_patterns(self) -> tuple[str, ...]:
        # TODO would be nice to get patterns from remote also in case agent was smart and added node_modules, etc.
        return (
            *(f"{pattern}/**" for pattern in _DEFAULT_FILETREE_EXCLUSIONS),
            *get_git_ignored_patterns_for_mutagen(self.local),
        )

    @property
    # TODO: revive when killed?
    def is_session_daemon_running(self) -> bool:
        return self.name in get_all_sculptor_mutagen_session_names()

    def _track_last_attempted_action(self, action: _LastAction) -> _LastAction | None:
        last = self._last_attempted_action
        self._last_attempted_action = action
        return last

    def create(self) -> None:
        match self._track_last_attempted_action("create"):
            case None:
                logger.trace("{}.create()", self.name)
            case "terminate":
                logger.trace("{}.create() after terminate: restarting session", self.name)
            case "create" | "flush":
                is_already_running = self.is_session_daemon_running
                # FIXME(michael): are these worth logging?  I've definitely seen them cause flakes in CI if this is at error level, esp during shutdown
                logger.debug(
                    "suspicious: {}.create() double-tapped, and is_session_daemon_running={}",
                    self.name,
                    is_already_running,
                )
                if is_already_running:
                    return

        alpha, beta, mode = self._mutagen_alpha_beta_and_mode
        create_controlled_mutagen_sync(
            session_name=self.name,
            sync_mode=mode,
            source_path_or_url=alpha,
            dest_path_or_url=beta,
            ignore_patterns=self._ignore_patterns,
            snapshot_guard=self.snapshot_guard,
        )

    def flush(self) -> None:
        self._track_last_attempted_action("flush")
        try:
            run_mutagen_cmd(
                command=["mutagen", "sync", "flush", self.name],
                snapshot_guard=self.snapshot_guard,
            )
        except ProcessError as e:
            # FIXME(michael): are these worth logging?  I've definitely seen them cause flakes in CI if this is at error level, esp during shutdown
            log_exception(e, "Failed to flush sync session {}", ExceptionPriority.LOW_PRIORITY, self.name)
            raise self.make_error(operation="flush", message=f"Failed to flush sync session {self.name}") from e

    def terminate(self, is_skipped_if_uncreated: bool = True) -> None:
        last_state = self._track_last_attempted_action("terminate")
        if last_state is None and is_skipped_if_uncreated:
            logger.trace("Skipping termination of uncreated & unrunning session {}", self.name)
            return None
        terminate_mutagen_session(self.name)

    def make_error(self, operation: str, message: str) -> MutagenSyncError:
        # TODO Consider adding _SyncStep
        return MutagenSyncError(
            operation=f"{self.sync_step}.{operation}",
            message=message,
            session_name=self.name,
            sync_mode=self._mutagen_alpha_beta_and_mode[2],
            source_path=str(self.local),
            dest_path=str(self.remote_mutagen_url),
        )

    def __del__(self) -> None:
        self.terminate()


def overwrite_local_with_remote_once(
    local_path: Path,
    remote_mutagen_url: str,
    session_name: str,
    snapshot_guard: ReadWriteLock | None = None,
) -> None:
    logger.debug("Creating initial one-way sync session to pull task changes...")
    session = MutagenSyncSession(
        name=session_name,
        local=local_path,
        remote_mutagen_url=remote_mutagen_url,
        sync_step=MutagenSyncStep.OVERWRITE_LOCAL_WITH_REMOTE,
        snapshot_guard=snapshot_guard,
    )
    session.create()
    logger.debug("Successfully created initial one-way sync session: {}", session.name)
    try:
        session.flush()
        logger.debug("Initial sync flush completed successfully")
    finally:
        session.terminate()
        logger.debug("Terminated initial sync session: {}", session.name)


def create_bidirectional_user_prioritized_sync(
    local_path: Path,
    remote_mutagen_url: str,
    session_name: str,
    snapshot_guard: ReadWriteLock | None = None,
) -> MutagenSyncSession:
    logger.debug("Creating mutagen sync session {}", session_name)
    session = MutagenSyncSession(
        name=session_name,
        local=local_path,
        remote_mutagen_url=remote_mutagen_url,
        sync_step=MutagenSyncStep.BIDIRECTIONAL_USER_ALWAYS_WINS,
        snapshot_guard=snapshot_guard,
    )
    session.create()
    session.flush()
    logger.debug("Successfully created mutagen session: {}", session.name)
    return session


# TODO: Has no tests
class LocalSyncGitStateGuardian(MutableModel):
    """Protect us from running `mutagen sync flush` while not on the correct git branch as much as possible

    Not foolproof - see: https://linear.app/imbue/issue/PROD-1680/custom-git-hook-to-guarantee-sync-transactionality
    """

    tag: str = LOCAL_GIT_STATE_GUARDIAN_TAG
    repo: LocalReadOnlyGitRepo
    branch_name: str

    @classmethod
    def build(cls, repo_path: Path, branch_name: str) -> "LocalSyncGitStateGuardian":
        repo = LocalReadOnlyGitRepo(repo_path=repo_path)
        return cls(repo=repo, branch_name=branch_name)

    def _generate_local_git_state_blockers(self) -> Generator[str, None, None]:
        is_in_multi_step_op = False
        if self.repo.is_rebase_in_progress:
            is_in_multi_step_op = True
            yield "rebase is in progress (finish or abort to resume)"
        if self.repo.is_merge_in_progress:
            is_in_multi_step_op = True
            yield "merge is in progress (finish or abort to resume)"
        if self.repo.is_cherry_pick_in_progress:
            is_in_multi_step_op = True
            yield "cherry-pick is in progress (finish or abort to resume)"

        # TODO: Not sure if we want to XOR with the above? But I think they aren't mutually exclusive
        current_branch = self.repo.get_current_git_branch()
        if current_branch == "HEAD":
            if not is_in_multi_step_op:
                yield f"detached HEAD state (switch back to `{self.branch_name}` to resume)"
            return
        if self.repo.get_current_git_branch() != self.branch_name:
            yield f"switched to `{self.repo.get_current_git_branch()}` (switch back to `{self.branch_name}` to resume)"

    def get_notices(self) -> tuple[LocalSyncNoticeUnion, ...]:
        return tuple(
            LocalSyncNoticeOfPause(
                source_tag=self.tag,
                reason=f"cannot sync filetree while {reason}",
            )
            for reason in self._generate_local_git_state_blockers()
        )

    def validate_state_is_acceptable(self) -> None:
        notices = self.get_notices()
        if len(notices) > 0:
            raise NewNoticesInSyncHandlingError(notices=notices)


class MutagenSyncSessionReconciler(MultiRootFiletreeSubPathReconciler):
    """
    NOTE: because we're watching both endpoints, each flush triggers another batch.
    This is fine - if that "echo" batch has no changes for $debounce_seconds, nothing will happen...
    aside from a single spurious "batch complete" message $debounce_seconds later.
    """

    tag: str = LOCAL_FILESYNC_TAG
    session: MutagenSyncSession
    guardian: LocalSyncGitStateGuardian
    stop_event: threading.Event

    def get_notices(self) -> tuple[LocalSyncNoticeUnion, ...]:
        git_state_notices = self.guardian.get_notices()
        # TODO surface conflicts as well
        return (*git_state_notices,)

    @property
    def root_paths(self) -> tuple[Path, Path]:
        return (self.session.local, self.session.remote_path)

    @property
    def local_dirs_to_watch(self) -> tuple[Path, ...]:
        return (self.session.local,)

    @property
    def environment_dirs_to_watch(self) -> tuple[Path, ...]:
        return (self.session.remote_path,)

    def flush_with_resurrection_if_dead(self) -> None:
        """The mutagen session is _ours_, so if it dies we refuse to admit defeat and resurrect it."""
        start = time.monotonic()
        try:
            self.session.flush()
        except MutagenSyncError as e:
            elapsed = time.monotonic() - start
            message = "mutagen flush error. elapsed={}s, is_stop_event_set={}, is_daemon_running={}"
            args = (elapsed, self.stop_event.is_set(), self.session.is_session_daemon_running)
            if self.stop_event.is_set():
                # we're probably in a race and probably is_session_daemon_running.
                # Report regardless, but the top-level session has taken control so we return.
                log_exception(e, message, ExceptionPriority.MEDIUM_PRIORITY, *args)
                return

            # not an emergency - probably some external issue
            logger.info(message, *args)

            # nothing killed mutagen but we have error - big problem/undefined state
            if self.session.is_session_daemon_running:
                raise

            # something killed mutagen that definitely wasn't us - boot up again and proceed
            self.session.create()

            # if this one fails then we just give up / pause.
            # This function will be called repeatedly in this case
            self.session.flush()

    def handle_path_changes(self, relevant_paths: tuple[Path, ...]) -> None:
        notices = self.get_notices()
        if len(notices) > 0:
            raise NewNoticesInSyncHandlingError(notices=notices)

        self.flush_with_resurrection_if_dead()
