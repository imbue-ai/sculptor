from typing import assert_never

from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.services.workspace_service.vcs.git_workspace_vcs import GitWorkspaceVcs
from sculptor.services.workspace_service.vcs.interfaces import WorkspaceVcs
from sculptor.services.workspace_service.vcs.vcs_runners import VcsRunners


def make_workspace_vcs(
    initialization_strategy: WorkspaceInitializationStrategy,
    runners: VcsRunners,
    concurrency_group: ConcurrencyGroup,
) -> WorkspaceVcs:
    """The version control for workspaces of this kind; the one place an implementation is chosen."""
    match initialization_strategy:
        case (
            WorkspaceInitializationStrategy.IN_PLACE
            | WorkspaceInitializationStrategy.CLONE
            | WorkspaceInitializationStrategy.WORKTREE
        ):
            return GitWorkspaceVcs(initialization_strategy, runners.git, concurrency_group)
        case _ as unreachable:
            assert_never(unreachable)
