from abc import ABC
from abc import abstractmethod
from pathlib import Path

from pydantic import AnyUrl

from sculptor.foundation.pydantic_serialization import MutableModel


class ReadOnlyGitRepo(MutableModel, ABC):
    """
    All read operations on a git repository should be done through this interface.

    Should all raise GitRepoNotFoundError if the repository does not exist.
    """

    @abstractmethod
    def get_repo_path(self) -> Path: ...

    @abstractmethod
    def get_repo_url(self) -> AnyUrl: ...

    @abstractmethod
    def get_all_branches(self) -> list[str]:
        """
        Get a list of all local branches in the repository.
        """

    @abstractmethod
    def get_current_commit_hash(self) -> str:
        """
        The output of `git rev-parse HEAD`.

        There may be other uncommitted or untracked changes in the repository.
        """

    @abstractmethod
    def get_current_git_branch(self) -> str: ...

    @abstractmethod
    def is_branch_ref(self, branch: str) -> bool: ...

    @abstractmethod
    def is_valid_branch_name(self, branch: str) -> bool:
        """Whether `branch` is a legal git branch name (per `git check-ref-format`)."""
        ...


class WritableGitRepo(ReadOnlyGitRepo, ABC):
    """
    All write operations on a git repository should be done through this interface.
    """

    @abstractmethod
    def _run_git(self, args: list[str]) -> str: ...
