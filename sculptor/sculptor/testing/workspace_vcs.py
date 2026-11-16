"""Real version control for tests that build environments or call the VCS seam directly."""

from functools import partial

from sculptor.database.workspace_enums import GitInitializationStrategy
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.jj_availability import find_ready_jj_binary
from sculptor.services.user_config.user_config import read_jj_snapshot_max_new_file_size_mib
from sculptor.services.workspace_service.vcs.git_cli import GitCli
from sculptor.services.workspace_service.vcs.interfaces import WorkspaceVcs
from sculptor.services.workspace_service.vcs.vcs_runners import VcsRunners
from sculptor.services.workspace_service.vcs.vcs_runners import build_vcs_runners
from sculptor.services.workspace_service.vcs.workspace_vcs_selection import make_workspace_vcs


def _make_test_dependency_management_service(concurrency_group: ConcurrencyGroup) -> DependencyManagementService:
    """A dependency service on `concurrency_group`, which must be active: checking jj's readiness runs jj."""
    return DependencyManagementService(concurrency_group=concurrency_group)


def _make_test_vcs_runners(
    concurrency_group: ConcurrencyGroup, dependency_management_service: DependencyManagementService
) -> VcsRunners:
    return build_vcs_runners(concurrency_group, dependency_management_service.resolve_binary_path)


def make_test_git_cli(concurrency_group: ConcurrencyGroup) -> GitCli:
    """A `GitCli` that runs the binaries the dependency service resolves, as the workspace service's does."""
    return _make_test_vcs_runners(concurrency_group, _make_test_dependency_management_service(concurrency_group)).git


def make_test_git_workspace_vcs(
    initialization_strategy: GitInitializationStrategy, concurrency_group: ConcurrencyGroup
) -> WorkspaceVcs:
    """The version control the workspace service gives a workspace of `initialization_strategy`."""
    return _make_test_workspace_vcs(initialization_strategy, concurrency_group)


def make_test_jj_workspace_vcs(concurrency_group: ConcurrencyGroup) -> WorkspaceVcs:
    """The version control the workspace service gives a jj workspace."""
    return _make_test_workspace_vcs(WorkspaceInitializationStrategy.JJ_WORKSPACE, concurrency_group)


def _make_test_workspace_vcs(
    initialization_strategy: WorkspaceInitializationStrategy, concurrency_group: ConcurrencyGroup
) -> WorkspaceVcs:
    dependency_management_service = _make_test_dependency_management_service(concurrency_group)
    return make_workspace_vcs(
        initialization_strategy,
        _make_test_vcs_runners(concurrency_group, dependency_management_service),
        concurrency_group,
        read_jj_snapshot_max_new_file_size_mib,
        partial(find_ready_jj_binary, dependency_management_service),
    )
