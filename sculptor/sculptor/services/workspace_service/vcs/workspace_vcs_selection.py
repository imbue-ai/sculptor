from typing import assert_never

from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.services.workspace_service.vcs.git_workspace_vcs import GitWorkspaceVcs
from sculptor.services.workspace_service.vcs.interfaces import WorkspaceVcs
from sculptor.services.workspace_service.vcs.jj_workspace_vcs import JjWorkspaceVcs
from sculptor.services.workspace_service.vcs.jj_workspace_vcs import ReadyJjBinaryReader
from sculptor.services.workspace_service.vcs.jj_workspace_vcs import SnapshotSizeLimitReader
from sculptor.services.workspace_service.vcs.vcs_runners import VcsRunners


def make_workspace_vcs(
    initialization_strategy: WorkspaceInitializationStrategy,
    runners: VcsRunners,
    concurrency_group: ConcurrencyGroup,
    read_jj_snapshot_max_new_file_size_mib: SnapshotSizeLimitReader,
    read_ready_jj_binary: ReadyJjBinaryReader,
) -> WorkspaceVcs:
    """The version control for workspaces of this kind; the one place an implementation is chosen.

    `read_jj_snapshot_max_new_file_size_mib` is the user's configured jj snapshot limit, and
    `read_ready_jj_binary` the jj that readiness accepts; each is read when it is needed.
    """
    match initialization_strategy:
        case (
            WorkspaceInitializationStrategy.IN_PLACE
            | WorkspaceInitializationStrategy.CLONE
            | WorkspaceInitializationStrategy.WORKTREE
        ):
            return GitWorkspaceVcs(initialization_strategy, runners.git, concurrency_group)
        case WorkspaceInitializationStrategy.JJ_WORKSPACE:
            return JjWorkspaceVcs(
                runners.jj, runners.git, read_jj_snapshot_max_new_file_size_mib, read_ready_jj_binary
            )
        case _ as unreachable:
            assert_never(unreachable)
