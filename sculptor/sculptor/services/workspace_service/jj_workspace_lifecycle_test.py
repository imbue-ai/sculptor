"""A jj workspace's lifecycle through the workspace service, against a real colocated repository and the real jj."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from sculptor.config.settings import SculptorSettings
from sculptor.config.settings import TEST_LOG_PATH
from sculptor.config.user_config import DependencyPaths
from sculptor.config.user_config import UserConfig
from sculptor.database.models import Project
from sculptor.database.models import Workspace
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.progress_tracking.progress_tracking import RootProgressHandle
from sculptor.primitives.constants import ANONYMOUS_ORGANIZATION_REFERENCE
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import TaskID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.user_config.user_config import set_user_config_instance
from sculptor.services.workspace_service.environment_manager import (
    default_implementation as environment_manager_default_implementation,
)
from sculptor.services.workspace_service.environment_manager.environments import local_environment
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjColocatedRepo
from sculptor.testing.jj_repos import run_jj
from sculptor.utils.shutdown import GLOBAL_SHUTDOWN_EVENT


@pytest.fixture
def test_settings(database_url: str, tmp_path: Path) -> SculptorSettings:
    """Keep diff artifacts under `tmp_path` instead of the developer's Sculptor folder."""
    artifacts_dir = tmp_path / "sculptor_artifacts"
    return SculptorSettings(
        DATABASE_URL=database_url,
        LOG_PATH=str(TEST_LOG_PATH),
        LOG_LEVEL="TRACE",
        SESSION_TOKEN=None,
        TASK_SYNC_DIR=str(artifacts_dir / "task_sync"),
        WORKSPACE_SYNC_DIR=str(artifacts_dir / "workspace_sync"),
    )


@pytest.fixture(autouse=True)
def _redirect_workspace_checkouts_to_tmp_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Create environments under `tmp_path`; both environment-manager modules read the directory at import time."""
    workspaces_dir = tmp_path / "workspaces"
    workspaces_dir.mkdir()
    monkeypatch.setattr(environment_manager_default_implementation, "LOCAL_WORKSPACE_DIR", workspaces_dir)
    monkeypatch.setattr(local_environment, "LOCAL_WORKSPACE_DIR", workspaces_dir)


@pytest.fixture
def jj_resolved_to_the_pinned_binary(jj_binary: JjBinary, silly_global_config: UserConfig) -> Iterator[None]:
    set_user_config_instance(
        silly_global_config.model_copy(update={"dependency_paths": DependencyPaths(jj=str(jj_binary.path))})
    )
    yield
    set_user_config_instance(None)


@pytest.fixture
def jj_project(
    jj_resolved_to_the_pinned_binary: None,
    jj_colocated_repo: JjColocatedRepo,
    test_service_collection: CompleteServiceCollection,
) -> Project:
    """A project for `jj_colocated_repo` that creates jj workspaces and runs no setup command."""
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        initialized = test_service_collection.project_service.initialize_project(
            project_path=jj_colocated_repo.path,
            organization_reference=ANONYMOUS_ORGANIZATION_REFERENCE,
            transaction=transaction,
        )
        test_service_collection.project_service.activate_project(initialized)
        project = transaction.update_project_fields(
            initialized.object_id, use_jj_for_new_workspaces=True, workspace_setup_command=""
        )
    assert project is not None
    return project


def _create_jj_workspace(
    test_service_collection: CompleteServiceCollection,
    project: Project,
    source_branch: str | None,
    requested_branch_name: str = "feature",
) -> Workspace:
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        return test_service_collection.workspace_service.create_workspace(
            project=project,
            initialization_strategy=WorkspaceInitializationStrategy.JJ_WORKSPACE,
            source_branch=source_branch,
            requested_branch_name=requested_branch_name,
            description="jj workspace",
            transaction=transaction,
        )


def _start_first_agent(
    test_service_collection: CompleteServiceCollection,
    project: Project,
    workspace: Workspace,
    concurrency_group: ConcurrencyGroup,
) -> Path:
    """Open the workspace's environment as an agent start does, and return its checkout."""
    with concurrency_group.make_concurrency_group("agent_environment") as agent_concurrency_group:
        with test_service_collection.workspace_service.agent_environment_context(
            project=project,
            workspace_id=workspace.object_id,
            task_id=TaskID(),
            concurrency_group=agent_concurrency_group,
            root_progress_handle=RootProgressHandle(),
            shutdown_event=GLOBAL_SHUTDOWN_EVENT,
        ) as agent_environment:
            return agent_environment.get_working_directory()


def _read_commit_id(jj_binary: JjBinary, repo_path: Path, revision: str) -> str:
    return run_jj(
        jj_binary, ("--ignore-working-copy", "log", "--no-graph", "-r", revision, "-T", "commit_id"), cwd=repo_path
    ).strip()


def test_a_jj_workspace_given_no_source_starts_from_its_default_target(
    jj_binary: JjBinary,
    jj_colocated_repo: JjColocatedRepo,
    jj_project: Project,
    test_service_collection: CompleteServiceCollection,
) -> None:
    """jj has no checked-out commit to fall back on, so the base is the target, and its commit is recorded."""
    workspace = _create_jj_workspace(test_service_collection, jj_project, source_branch=None)

    trunk = f"{jj_colocated_repo.default_bookmark}@origin"
    assert workspace.target_branch == trunk
    assert workspace.source_branch == trunk
    assert workspace.source_git_hash == _read_commit_id(jj_binary, jj_colocated_repo.path, trunk)


def test_a_jj_workspace_given_a_commit_id_starts_from_that_commit(
    jj_binary: JjBinary,
    jj_colocated_repo: JjColocatedRepo,
    jj_project: Project,
    test_service_collection: CompleteServiceCollection,
) -> None:
    root_commit_id = _read_commit_id(jj_binary, jj_colocated_repo.path, "root()")

    workspace = _create_jj_workspace(test_service_collection, jj_project, source_branch=root_commit_id)

    assert workspace.source_branch == root_commit_id
    assert workspace.source_git_hash == root_commit_id


def test_the_first_agent_start_creates_a_jj_only_checkout_on_the_workspaces_base(
    jj_binary: JjBinary,
    jj_colocated_repo: JjColocatedRepo,
    jj_project: Project,
    test_service_collection: CompleteServiceCollection,
    test_root_concurrency_group: ConcurrencyGroup,
) -> None:
    workspace = _create_jj_workspace(test_service_collection, jj_project, source_branch=None)

    checkout = _start_first_agent(test_service_collection, jj_project, workspace, test_root_concurrency_group)

    assert (checkout / ".jj" / "repo").is_file()
    assert not (checkout / ".git").exists()
    assert (checkout / "README.md").is_file()
    assert _read_commit_id(jj_binary, checkout, "@-") == workspace.source_git_hash
    workspace_names = run_jj(jj_binary, ("workspace", "list", "-T", 'name ++ "\\n"'), cwd=jj_colocated_repo.path)
    assert str(workspace.object_id) in workspace_names.split()
