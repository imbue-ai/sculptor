"""Real version control for tests that build environments or call the VCS seam directly."""

from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.workspace_service.vcs.git_cli import GitCli
from sculptor.services.workspace_service.vcs.git_workspace_vcs import GitWorkspaceVcs


def make_test_git_cli(concurrency_group: ConcurrencyGroup) -> GitCli:
    """A `GitCli` that runs the binaries the dependency service resolves, as the workspace service's does."""
    dependency_management_service = DependencyManagementService(
        concurrency_group=concurrency_group.make_concurrency_group("dependency_management_service"),
    )
    return GitCli(concurrency_group, dependency_management_service.resolve_binary_path)


def make_test_git_workspace_vcs(
    initialization_strategy: WorkspaceInitializationStrategy, concurrency_group: ConcurrencyGroup
) -> GitWorkspaceVcs:
    """The git version control the workspace service gives a workspace of `initialization_strategy`."""
    return GitWorkspaceVcs(initialization_strategy, make_test_git_cli(concurrency_group), concurrency_group)
