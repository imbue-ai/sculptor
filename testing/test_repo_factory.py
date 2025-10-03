"""Factory for creating test repositories on demand."""

from __future__ import annotations

from pathlib import Path

from sculptor.testing.mock_repo import MockRepoState
from sculptor.testing.repo_resources import get_test_project_state


class TestRepoFactory:
    """Factory for creating test repositories on demand.

    This factory provides methods to create test repositories with different
    configurations. Each repository is created in a temporary directory that's
    automatically cleaned up after the test.
    """

    def __init__(self, base_path: Path) -> None:
        """Initialize the factory with a base temporary path.

        Args:
            base_path: The temporary directory where repositories will be created
        """
        self.base_path = base_path
        self.created_repos: list[MockRepoState] = []

    def create_repo(
        self,
        name: str,
        branch: str,
    ) -> MockRepoState:
        """Create a test repository with the given configuration.

        Args:
            name: Name of the project directory
            branch: Branch name to create and checkout

        Returns:
            MockRepoState instance for the created repository
        """
        repo_dir = self.base_path / name

        # Get the standard test project state
        initial_state = get_test_project_state()

        # Build the repository
        repo = MockRepoState.build_locally(state=initial_state, local_dir=repo_dir)

        repo.create_reset_and_checkout_branch(branch)
        # Add a commit on the branch to differentiate it
        repo.write_file(f"{name}_file.txt", f"This is {name} on {branch}")
        repo.commit(f"Add {name} specific file on {branch}")

        # Track for potential debugging
        self.created_repos.append(repo)

        return repo
