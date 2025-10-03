from abc import ABC
from abc import abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from pydantic import AnyUrl
from pydantic import computed_field

from imbue_core.pydantic_serialization import MutableModel
from imbue_core.pydantic_serialization import SerializableModel
from sculptor.database.models import Project
from sculptor.primitives.ids import UserReference
from sculptor.primitives.service import Service


def is_git_merge_result_up_to_date(stdout: str) -> bool:
    # from man git-merge:
    # > If all named commits are already ancestors of HEAD, git merge will exit early with the message "Already up to date."
    return stdout.strip() == "Already up to date."


class AbsoluteGitReference(SerializableModel):
    """Pointer to a specific commit within a specific context in a git repository."""

    repo_url: AnyUrl
    branch: str  # note: detatched HEAD unsupported
    commit_hash: str

    def describe(self) -> str:
        return f"commit {self.commit_hash} on branch {self.branch} in repository {self.repo_url}"


class GitRepoFileStatus(SerializableModel):
    unstaged: int
    staged: int
    untracked: int
    deleted: int
    ignored: int

    @computed_field
    @property
    def are_clean_including_untracked(self) -> bool:
        return all((f == 0 for f in (self.unstaged, self.staged, self.deleted, self.untracked)))

    @computed_field
    @property
    def description(self) -> str:
        if self.are_clean_including_untracked:
            return "no changed or unstaged files"

        maybe_description = lambda count, name: f"{count} {name} file{'s' if count > 1 else ''}" if count > 0 else None
        return "\n".join(
            filter(
                None,
                (
                    maybe_description(self.unstaged, "unstaged"),
                    maybe_description(self.staged, "staged"),
                    maybe_description(self.untracked, "untracked"),
                    maybe_description(self.deleted, "deleted"),
                ),
            )
        )


class GitRepoStatus(SerializableModel):
    """
    Current status of a git repository.

    Contains information about the working directory state, including
    merge/rebase/cherry-pick status and file change counts.
    """

    files: GitRepoFileStatus
    is_merging: bool
    is_rebasing: bool
    is_cherry_picking: bool

    @computed_field
    @property
    def is_in_intermediate_state(self) -> bool:
        return self.is_merging or self.is_rebasing or self.is_cherry_picking

    @computed_field
    @property
    def is_clean_and_safe_to_operate_on(self) -> bool:
        return self.files.are_clean_including_untracked and not self.is_in_intermediate_state

    def describe(self, is_file_changes_list_included: bool = True) -> str:
        ops_in_progress = []
        if self.is_merging:
            ops_in_progress.append("merge in progress")
        if self.is_rebasing:
            ops_in_progress.append("rebase in progress")
        if self.is_cherry_picking:
            ops_in_progress.append("cherry-pick in progress")

        ops = ", ".join(ops_in_progress) if ops_in_progress else "no operations in progress"
        if not is_file_changes_list_included:
            return ops
        return f"{ops}, \n{self.files.description}"


class GitRepoMergeResult(SerializableModel):
    is_merged: bool
    is_stopped_by_uncommitted_changes: bool = False
    was_up_to_date: bool = False
    is_aborted: bool = False

    raw_output: str

    @computed_field
    @property
    def description(self) -> str:
        if self.is_merged:
            if self.was_up_to_date:
                return "already up to date"
            else:
                return "merge successful"
        elif self.is_aborted:
            return "merge resulted in conflicts and was aborted"
        elif self.is_stopped_by_uncommitted_changes:
            return "uncommitted changes are blocking the merge"
        else:
            return "merge resulted in conflicts"


class ReadOnlyGitRepo(MutableModel, ABC):
    """
    All read operations on a git repository should be done through this interface.

    Should all raise FileNotFoundError if the repository does not exist.
    """

    @abstractmethod
    def get_repo_path(self) -> Path: ...

    @abstractmethod
    def get_repo_url(self) -> AnyUrl: ...

    @property
    def is_bare_repo(self) -> bool: ...

    # TODO: how recent is recent? parameterize this?  recently modified?
    @abstractmethod
    def get_recent_branches(self) -> list[str]:
        """
        Get a list of recent branches in the repository.
        """

    @abstractmethod
    def get_current_commit_hash(self) -> str:
        """
        The output of `git rev-parse HEAD`

        Obviously there may be other current (uncommitted or untracked) changes in the repository,
        """

    @abstractmethod
    def get_branch_head_commit_hash(self, branch_name: str) -> str:
        """
        Get the commit hash of the head of the specified branch.
        """

    @abstractmethod
    def get_current_git_branch(self) -> str: ...

    @abstractmethod
    def export_current_repo_state(self, target_folder: Path) -> str: ...

    @abstractmethod
    def get_absolute_reference_to_current_location(self) -> AbsoluteGitReference: ...

    @abstractmethod
    def get_num_uncommitted_changes(self) -> int: ...

    @abstractmethod
    def is_branch_ref(self, branch: str) -> bool: ...

    @abstractmethod
    def list_matching_folders(self, pattern: str = "") -> list[str]:
        """
        List all folders in the repository.
        """

    @abstractmethod
    def list_matching_files(self, pattern: str | None) -> list[str]:
        """
        List all files in the repository.
        """

    @abstractmethod
    def list_untracked_files(self) -> list[str]: ...

    @abstractmethod
    def read_file(self, repo_relative_path: Path) -> str | None:
        """
        Return the contents of the file at the current commit (or None if the file does not exist).
        """

    @property
    @abstractmethod
    def is_merge_in_progress(self) -> bool: ...

    @property
    @abstractmethod
    def is_rebase_in_progress(self) -> bool: ...

    @property
    @abstractmethod
    def is_cherry_pick_in_progress(self) -> bool: ...

    @abstractmethod
    def get_current_status(
        self, is_read_only_and_lockless: bool = False, additional_ignores: tuple[str, ...] | None = None
    ) -> GitRepoStatus:
        """
        Get the current status of the git repository.

        Returns information about the working directory state, including
        merge/rebase status and file change counts.
        """


class WritableGitRepo(ReadOnlyGitRepo, ABC):
    """
    All write operations on a git repository should be done through this interface.
    """

    @abstractmethod
    def maybe_fetch_remote_branch_into_local(
        self,
        local_branch: str,
        remote: AnyUrl,
        remote_branch: str,
        dry_run: bool = False,
        force: bool = False,
        dangerously_update_head_ok: bool = False,
    ) -> bool: ...

    @abstractmethod
    def merge_from_ref(self, ref: str, commit_message: str | None = None) -> GitRepoMergeResult:
        """Merge the given ref into current checkout.

        Does not re-raise any git operation errors.
        """
        ...

    @abstractmethod
    def pull_from_remote(
        self,
        remote: str,
        remote_branch: str,
        should_abort_on_conflict: bool = False,
        is_fast_forward_only: bool = False,
        assert_local_branch_equals_to: str | None = None,
    ) -> GitRepoMergeResult: ...

    @abstractmethod
    def ensure_local_branch_has_remote_branch_ref(self, remote_repo: AnyUrl, remote_branch: str) -> bool: ...

    @abstractmethod
    def create_git_stash(self, stash_message: str) -> bool:
        """Create a git stash and return whether any changes were stashed."""
        ...

    @abstractmethod
    def git_checkout_branch(self, branch_name: str) -> None:
        """Checkout a git branch."""
        ...

    @abstractmethod
    def reset_working_directory(self) -> None:
        """Reset working directory to clean state."""
        ...

    @abstractmethod
    def restore_git_stash(self, stash_message: str) -> None:
        """Restore a specific git stash by finding it using the unique message."""
        ...


class GitRepoService(Service, ABC):
    """
    Provides an interface to the user's local git repository.

    All interactions with that repository should be done through this service.

    The two different context managers are mostly for convention, to declare your intent when accessing the repository.
    """

    @abstractmethod
    @contextmanager
    def open_local_user_git_repo_for_read(
        self, user_reference: UserReference, project: Project
    ) -> Generator[ReadOnlyGitRepo, None, None]:
        """
        Open a local git repository for read access.

        Note that this access is exclusive --
        no other threads or processes will be able to access the repository while inside the context manager.

        This does *not* mean that there will be no concurrent access to the repository
        (because the user may, at any time, cause git commands to run on the repository).
        """

    @abstractmethod
    @contextmanager
    def open_local_user_git_repo_for_write(
        self, user_reference: UserReference, project: Project
    ) -> Generator[WritableGitRepo, None, None]:
        """
        Open a local git repository for write access.

        Note that this access is exclusive --
        no other threads or processes will be able to access the repository while inside the context manager.

        This does *not* mean that there will be no concurrent access to the repository
        (because the user may, at any time, cause git commands to run on the repository).
        """
