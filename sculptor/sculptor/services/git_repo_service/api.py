from abc import ABC
from abc import abstractmethod
from contextlib import contextmanager
from typing import Generator

from sculptor.database.models import Project
from sculptor.primitives.service import Service
from sculptor.services.git_repo_service.git_repos import ReadOnlyGitRepo


class GitRepoService(Service, ABC):
    """
    Provides an interface to the user's local git repository.

    All interactions with that repository should be done through this service.
    """

    @abstractmethod
    @contextmanager
    def open_local_user_git_repo_for_read(
        self, project: Project, log_command: bool = True
    ) -> Generator[ReadOnlyGitRepo, None, None]:
        """
        Open a local git repository for read access.

        Multiple readers may hold this concurrently, but readers are excluded while a writer is active.

        This does *not* mean that there will be no concurrent access to the repository
        (because the user may, at any time, cause git commands to run on the repository).
        """
