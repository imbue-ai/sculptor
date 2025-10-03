import uuid
from abc import abstractmethod
from functools import cached_property
from pathlib import Path
from typing import Any
from typing import Final
from typing import Generic
from typing import TypeVar
from typing import cast

from loguru import logger
from pydantic import AnyUrl

from sculptor.interfaces.agents.v1.agent import LocalSyncNoticeOfPause
from sculptor.interfaces.agents.v1.agent import LocalSyncNoticeUnion
from sculptor.interfaces.environments.v1.base import Environment
from sculptor.primitives.service import MutableModel
from sculptor.services.git_repo_service.default_implementation import LocalWritableGitRepo
from sculptor.services.git_repo_service.default_implementation import RemoteReadOnlyGitRepo
from sculptor.services.git_repo_service.error_types import GitRepoError
from sculptor.services.local_sync_service.data_types import NewNoticesInSyncHandlingError
from sculptor.services.local_sync_service.path_batch_scheduler import LocalSyncSubReconciler
from sculptor.services.local_sync_service.path_batch_scheduler import is_pause_necessary

RepoT = TypeVar("RepoT", bound=LocalWritableGitRepo | RemoteReadOnlyGitRepo)

LOCAL_GIT_SYNC_TAG: Final = "local_git_sync"

_REPORT_TO_SENTRY_AFTER_MAX_EVENTS_SINCE_LAST_CHANGE: Final = 100_000


def unwrap_url_path(url: AnyUrl) -> Path:
    if url.scheme != "file":
        raise ValueError(f"Expected a file:// URL, got {url}")
    assert url.path is not None
    return Path(url.path)


class FileContentDivergenceReconciler(LocalSyncSubReconciler):
    "base class for GitBranchSyncReconciler to make the file-watching interface more visible"

    _last_seen_contents: dict[Path, str] = {}
    _events_since_last_change: int = 0
    _is_suspicious_watcher_already_reported: bool = False

    def _fallback_to_cache(self, path: Path, content: str | None) -> str:
        if content is None:
            # IDK if this is necessary but we eventually want an in-memory hash log list anyhow and this is a decent start to that
            logger.trace("File missing (hopefully temporarily), returning last seen content for {}", path)
            return self._last_seen_contents[path]
        if self._last_seen_contents.get(path) != content:
            self._last_seen_contents[path] = content
            self._events_since_last_change = 0
        return content

    def _track_events_and_report_if_watcher_suspicious(self):
        self._events_since_last_change += 1
        if (
            self._is_suspicious_watcher_already_reported
            or _REPORT_TO_SENTRY_AFTER_MAX_EVENTS_SINCE_LAST_CHANGE is None
            or self._events_since_last_change < _REPORT_TO_SENTRY_AFTER_MAX_EVENTS_SINCE_LAST_CHANGE
        ):
            return
        message = f"SUSPICIOUS_LOCAL_SYNC_STATE: Too many git sync file events! {self._events_since_last_change=} > {_REPORT_TO_SENTRY_AFTER_MAX_EVENTS_SINCE_LAST_CHANGE=}"
        logger.error(message)
        self._is_suspicious_watcher_already_reported = True

    @property
    def exact_paths_to_react_to(self) -> tuple[Path, ...]:
        raise NotImplementedError()

    @abstractmethod
    def is_relevant_subpath(self, path: Path) -> bool: ...


def _push_and_fetch_into_environment_repo_using_temp_branch(
    repo: RemoteReadOnlyGitRepo, from_user_repo: AnyUrl, head_ref: str, is_dangerously_updating_head: bool
) -> None:
    tmp_branch = str(uuid.uuid4())
    repo.environment.push_into_environment_repo(unwrap_url_path(from_user_repo), head_ref, tmp_branch)
    cmd = ["fetch", "--show-forced-updates"]
    if is_dangerously_updating_head:
        cmd.append("--update-head-ok")
    cmd.extend([".", f"{tmp_branch}:{head_ref}"])
    repo._run_git(cmd)
    repo._run_git(["branch", "-D", tmp_branch])


def _fetch_into_user_branch_from_agent(
    repo: LocalWritableGitRepo, from_agent_repo: AnyUrl, head_ref: str, is_dangerously_updating_head: bool
) -> None:
    # TODO this should use self.maybe_fetch_remote_branch_into_local but needs to rais it's error or something similar
    cmd = ["fetch", "--show-forced-updates"]
    if is_dangerously_updating_head:
        cmd.append("--update-head-ok")
    cmd.extend([str(from_agent_repo), f"{head_ref}:{head_ref}"])
    repo._run_git(cmd)


class _BranchSyncRepo(MutableModel, Generic[RepoT]):
    """A git repository wrapper with convenience utilities for syncing.

    Note that while we wrap "read-only" repos, we do apply modifications
    """

    repo: RepoT
    branch_name: str

    @property
    def url(self) -> AnyUrl:
        return self.repo.get_repo_url()

    def _run_git(self, args: list[str]) -> str:
        return self.repo._run_git(args)

    # just referred a lot in testing
    def get_current_commit_hash(self) -> str:
        return self.repo.get_current_commit_hash()

    @property
    def head_ref(self) -> str:
        # NOTE: NO ADDING "+" HERE
        return f"refs/heads/{self.branch_name}"

    @property
    def head_refs_relpath(self) -> Path:
        return Path("refs/heads" if self.repo.is_bare_repo else ".git/refs/heads")

    @property
    def head_refs_dir(self) -> Path:
        """Get the path to the internal git refs directory."""
        if isinstance(self.repo, RemoteReadOnlyGitRepo):
            return Path(self.repo.get_internal_environment_path_str(self.head_refs_relpath))
        return self.repo.repo_path / self.head_refs_relpath

    @property
    def head_ref_pointer_relpath(self) -> Path:
        """Get the path to the internal git ref file for the current HEAD."""
        return self.head_refs_relpath / self.branch_name

    @cached_property
    def head_ref_pointer_internal_untrustworthy_abspath(self) -> Path:
        if isinstance(self.repo, RemoteReadOnlyGitRepo):
            env_internal_path = self.repo.get_internal_environment_path_str(self.head_ref_pointer_relpath)
            return Path(env_internal_path)
        return self.repo.repo_path / self.head_ref_pointer_relpath

    @property
    def head_ref_pointer_file_and_existence(self) -> tuple[Path, bool]:
        if isinstance(self.repo, RemoteReadOnlyGitRepo):
            env_internal_path = self.repo.get_internal_environment_path_str(self.head_ref_pointer_relpath)
            return Path(env_internal_path), self.repo.environment.exists(env_internal_path)
        local_path = self.repo.repo_path / self.head_ref_pointer_relpath
        return local_path, local_path.exists()

    def read_head_ref_content(self) -> str | None:
        return self.repo.read_file(self.head_ref_pointer_relpath)

    @property
    def head_ref_pointer_file_last_modified(self) -> float:
        if isinstance(self.repo, RemoteReadOnlyGitRepo):
            env_internal_path = self.repo.get_internal_environment_path_str(self.head_ref_pointer_relpath)
            return self.repo.environment.get_file_mtime(env_internal_path)
        return (self.repo.repo_path / self.head_ref_pointer_relpath).stat().st_mtime

    def get_branch_head_commit(self) -> str:
        return self.repo.get_branch_head_commit_hash(branch_name=self.branch_name)

    def is_this_branch_child_of(self, commit: str) -> bool:
        try:
            s = self._run_git(["merge-base", "--is-ancestor", commit, self.head_ref])
            return True
        except GitRepoError:
            return False

    # TODO reconcile with fetch_branch???
    def get_commits_into_wrapped_repo_branch(
        self, from_remote: AnyUrl, is_dangerously_updating_head: bool = False
    ) -> None:
        if isinstance(self.repo, LocalWritableGitRepo):
            _fetch_into_user_branch_from_agent(self.repo, from_remote, self.head_ref, is_dangerously_updating_head)
            return
        _push_and_fetch_into_environment_repo_using_temp_branch(
            self.repo, from_remote, self.head_ref, is_dangerously_updating_head
        )

    def fetch_and_reset_mixed_on_branch(self, from_remote: AnyUrl) -> None:
        """Fetch from remote and reset to match remote state."""
        head_before_fetch = self.get_branch_head_commit()

        is_sync_branch_checked_out = self.repo.get_current_git_branch() == self.branch_name
        if not is_sync_branch_checked_out:
            # TODO consider aborting here - should be harmless but also not valuable
            logger.debug(
                "git_branch_sync: repo {} changed branches from {}, just fetching",
                self.url,
                self.branch_name,
            )

        self.get_commits_into_wrapped_repo_branch(
            from_remote=from_remote, is_dangerously_updating_head=is_sync_branch_checked_out
        )

        if not is_sync_branch_checked_out:
            return

        is_already_up_to_date_thus_no_reason_to_reset = head_before_fetch == self.get_branch_head_commit()
        if is_already_up_to_date_thus_no_reason_to_reset:
            logger.debug("No change in head after fetch from remote: {}", from_remote)
            return

        if self.repo.get_current_git_branch() != self.branch_name:
            logger.debug(
                "git_branch_sync: {} != {}, not resetting", self.repo.get_current_git_branch(), self.branch_name
            )
            return

        logger.debug("Change in head after fetch from remote: {}, running reset --mixed", from_remote)

        # Reset to match the fetched state (mixed reset keeps working directory changes)
        # TODO: We could actually be more granular in our reset and only reset files that changed in the synced commit(s)
        self._run_git(["reset", "--mixed", self.head_ref])

        logger.debug("Successfully fetched and reset from remote {} into {}", from_remote, self.url)


class RepoBranchSyncReconciler(FileContentDivergenceReconciler):
    """Synchronizes git branch states between user and agent repositories.

    Will sync and validate branch consistency on initialization.
    """

    branch_name: str
    user_repo: _BranchSyncRepo[LocalWritableGitRepo]
    agent_repo: _BranchSyncRepo[RemoteReadOnlyGitRepo]
    tag: str = LOCAL_GIT_SYNC_TAG

    def model_post_init(self, context: Any) -> None:
        try:
            self.user_repo.repo.ensure_local_branch_has_remote_branch_ref(self.agent_repo.url, self.branch_name)
        except GitRepoError as e:
            message = f"Likely invalid branch: Failed to ensure {self.user_repo.url} had a reference to {self.branch_name} of agent repo {self.agent_repo.url}"
            raise AssertionError(message) from e
        user_ref, user_ref_exists = self.user_repo.head_ref_pointer_file_and_existence
        agent_ref, agent_ref_exists = self.agent_repo.head_ref_pointer_file_and_existence
        assert user_ref_exists and agent_ref_exists, (
            f"Some head ref paths don't exist: {user_ref}.exists()={user_ref_exists}, {agent_ref}.exists()={agent_ref_exists}"
        )
        last_seen_contents = {
            user_ref: self.user_repo.read_head_ref_content(),
            agent_ref: self.agent_repo.read_head_ref_content(),
        }
        assert None not in last_seen_contents.values(), (
            f"strange: refs exist but one returned None on read attempt ({last_seen_contents=})"
        )
        self._last_seen_contents = cast(dict[Path, str], last_seen_contents)

    @classmethod
    def build(
        cls, branch_name: str, user_repo_path: Path, agent_environment: Environment
    ) -> "RepoBranchSyncReconciler":
        return cls(
            branch_name=branch_name,
            user_repo=_BranchSyncRepo(repo=LocalWritableGitRepo(repo_path=user_repo_path), branch_name=branch_name),
            agent_repo=_BranchSyncRepo(
                repo=RemoteReadOnlyGitRepo(environment=agent_environment), branch_name=branch_name
            ),
        )

    @property
    def is_currently_easily_syncable(self) -> bool:
        """Check if the user and agent heads are currently easily syncable."""
        if not self.is_user_head_different_from_agent_head():
            return True
        other_repo, likely_changed_repo = sorted(
            (self.user_repo, self.agent_repo), key=lambda r: r.head_ref_pointer_file_last_modified
        )
        if other_repo.is_this_branch_child_of(likely_changed_repo.get_branch_head_commit()):
            return True
        if likely_changed_repo.is_this_branch_child_of(other_repo.get_branch_head_commit()):
            return True
        return False

    def _notice_if_repos_missing_ref_files(self) -> LocalSyncNoticeOfPause | None:
        "in case the user deleted the ref file or something"
        refs = (repo.head_ref_pointer_file_and_existence for repo in (self.user_repo, self.agent_repo))
        repos_missing_ref_file = tuple(ref for ref, exists in refs if not exists)
        if len(repos_missing_ref_file) == 0:
            return None
        reason = f"ref for {self.branch_name} missing in repo {repos_missing_ref_file[0]}"
        if len(repos_missing_ref_file) == 2:
            reason += f" and {repos_missing_ref_file[1]}"
        return LocalSyncNoticeOfPause(source_tag=self.tag, reason=reason)

    def get_notices(self) -> tuple[LocalSyncNoticeUnion, ...]:
        notice_missing_ref_file = self._notice_if_repos_missing_ref_files()
        if notice_missing_ref_file is not None:
            return (notice_missing_ref_file,)

        if self.is_currently_easily_syncable:
            return tuple()
        local_head = self.user_repo.get_branch_head_commit()[:8]
        remote_head = self.agent_repo.get_branch_head_commit()[:8]
        return (
            LocalSyncNoticeOfPause(
                source_tag=self.tag,
                reason=f"local head@{local_head} and agent head@{remote_head} require manual merging",
            ),
        )

    def _describe_sync_process(self) -> str:
        return f"git_local_sync of {self.branch_name}: {self.user_repo.url} <-> {self.agent_repo.url}"

    def fetch_and_reset_mixed_with_reverse_retry(self, to_repo: _BranchSyncRepo, from_repo: _BranchSyncRepo) -> None:
        try:
            # will succeed if to is behind from
            to_repo.fetch_and_reset_mixed_on_branch(from_remote=from_repo.url)
        except GitRepoError as e:
            logger.debug(
                "Initial fetch and reset failed from {} - attempting reverse operation just in case",
                from_repo.url,
            )
            logger.trace("Initial fetch and reset failed from {} failed because: {}", from_repo.url, e)
            # will succeed if from is behind to. Otherwise we have a conflict or race or something
            from_repo.fetch_and_reset_mixed_on_branch(from_remote=to_repo.url)
            logger.debug(
                "Successfully completed reverse fetch and reset from {} to {}",
                to_repo.url,
                from_repo.url,
            )

    def _summarize_hash_states(self) -> str:
        user_commit = self.user_repo.get_branch_head_commit()
        agent_commit = self.agent_repo.get_branch_head_commit()
        return f"user@{user_commit[:8]} agent@{agent_commit[:8]}"

    def is_user_head_different_from_agent_head(self) -> bool:
        return self.user_repo.get_branch_head_commit() != self.agent_repo.get_branch_head_commit()

    def is_user_head_equal_to_agent_head(self) -> bool:
        return not self.is_user_head_different_from_agent_head

    def is_user_a_fastforward_ahead_of_agent(self) -> bool:
        # children are ahead
        return self.user_repo.is_this_branch_child_of(self.agent_repo.get_branch_head_commit())

    def is_agent_a_fastforward_ahead_of_user(self) -> bool:
        # children are ahead
        return self.agent_repo.is_this_branch_child_of(self.user_repo.get_branch_head_commit())

    def sync_heads(self, changed_path: Path) -> bool:
        """Synchronize the HEAD states between user, agent repos.
        Returns True if a sync was performed, False if not.

        Because FileContentDivergenceReconciler.is_path_relevant handles event filtering based on ref divergence,
        we should pretty much always have different heads here.
        """
        missing_notice = self._notice_if_repos_missing_ref_files()
        if missing_notice:
            raise NewNoticesInSyncHandlingError((missing_notice,))

        summary = self._summarize_hash_states()

        # NOTE: Because we kicked content-difference back to the parent class via is_any_path_divergent,
        # we should never get here with an unfinished commit due to overly-wide change event handling.
        #
        # BUT, I'm keeping this for safety for now
        if not self.is_user_head_different_from_agent_head():
            logger.trace("head commits equal despite change signal in {}, skipping sync ({})", changed_path, summary)
            return False

        match changed_path:
            case self.user_repo.head_ref_pointer_internal_untrustworthy_abspath:
                logger.debug("user change triggered sync_heads on {} {}", self.branch_name, summary)
                self.fetch_and_reset_mixed_with_reverse_retry(to_repo=self.agent_repo, from_repo=self.user_repo)

            case self.agent_repo.head_ref_pointer_internal_untrustworthy_abspath:
                logger.debug("agent change triggered sync_heads on {} {}", self.branch_name, summary)
                self.fetch_and_reset_mixed_with_reverse_retry(to_repo=self.user_repo, from_repo=self.agent_repo)

            case _:
                raise ValueError(f"{LOCAL_GIT_SYNC_TAG}: Unexpected {changed_path=} (should be impossible)")

        logger.debug("sync_heads complete: {}", self._summarize_hash_states())
        return True

    @property
    def dirs_to_watch(self) -> tuple[Path, ...]:
        """Directories to watch for changes."""
        return (self.user_repo.head_refs_dir, self.agent_repo.head_refs_dir)

    @property
    def environment_dirs_to_watch(self) -> tuple[Path, ...]:
        return (self.agent_repo.head_refs_dir,)

    @property
    def local_dirs_to_watch(self) -> tuple[Path, ...]:
        return (self.user_repo.head_refs_dir,)

    @property
    def exact_paths_to_react_to(self) -> tuple[Path, ...]:
        return (
            self.user_repo.head_ref_pointer_internal_untrustworthy_abspath,
            self.agent_repo.head_ref_pointer_internal_untrustworthy_abspath,
        )

    def handle_path_changes(self, relevant_paths: tuple[Path, ...]) -> None:
        try:
            self.sync_heads(changed_path=relevant_paths[0])
        except GitRepoError as e:
            notices = self.get_notices()
            if is_pause_necessary(notices):
                raise NewNoticesInSyncHandlingError(notices) from e
            raise e

    def is_relevant_subpath(self, path: Path) -> bool:
        if path not in self.exact_paths_to_react_to:
            return False
        unique_contents = {
            self._fallback_to_cache(repo.head_ref_pointer_internal_untrustworthy_abspath, repo.read_head_ref_content())
            for repo in (self.user_repo, self.agent_repo)
        }
        is_any_path_divergent = len(unique_contents) > 1
        if not is_any_path_divergent:
            self._track_events_and_report_if_watcher_suspicious()
            logger.debug(
                "Ignoring event: No divergence of paths {} ({} since last change)",
                self.exact_paths_to_react_to,
                self._events_since_last_change,
            )
            return False
        return is_any_path_divergent
