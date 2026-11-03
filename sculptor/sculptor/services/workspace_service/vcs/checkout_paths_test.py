from pathlib import Path

from sculptor.database.models import Workspace
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.primitives.constants import ANONYMOUS_ORGANIZATION_REFERENCE
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import WorkspaceID
from sculptor.services.workspace_service.vcs.checkout_paths import workspace_checkout_path


def _make_workspace(strategy: WorkspaceInitializationStrategy, environment_id: str | None) -> Workspace:
    return Workspace(
        object_id=WorkspaceID(),
        project_id=ProjectID(),
        organization_reference=ANONYMOUS_ORGANIZATION_REFERENCE,
        description="test",
        initialization_strategy=strategy,
        environment_id=environment_id,
    )


def test_in_place_workspace_checks_out_the_repository_itself(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    with_environment = _make_workspace(WorkspaceInitializationStrategy.IN_PLACE, str(tmp_path / "env"))
    without_environment = _make_workspace(WorkspaceInitializationStrategy.IN_PLACE, None)

    assert workspace_checkout_path(with_environment, repo) == repo
    assert workspace_checkout_path(without_environment, repo) == repo


def test_clone_and_worktree_workspaces_check_out_into_the_environment_code_directory(tmp_path: Path) -> None:
    environment = tmp_path / "env"
    for strategy in (WorkspaceInitializationStrategy.CLONE, WorkspaceInitializationStrategy.WORKTREE):
        workspace = _make_workspace(strategy, str(environment))

        assert workspace_checkout_path(workspace, tmp_path / "repo") == environment / "code"


def test_isolated_workspace_without_an_environment_has_no_checkout_yet(tmp_path: Path) -> None:
    for strategy in (WorkspaceInitializationStrategy.CLONE, WorkspaceInitializationStrategy.WORKTREE):
        workspace = _make_workspace(strategy, None)

        assert workspace_checkout_path(workspace, tmp_path / "repo") is None


def test_workspace_checkout_path_never_touches_the_filesystem(tmp_path: Path) -> None:
    missing_environment = tmp_path / "deleted-env"
    workspace = _make_workspace(WorkspaceInitializationStrategy.WORKTREE, str(missing_environment))

    assert workspace_checkout_path(workspace, tmp_path / "repo") == missing_environment / "code"
    assert not missing_environment.exists()
