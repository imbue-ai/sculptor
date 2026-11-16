"""A jj workspace's lifecycle through the workspace service, against a real colocated repository and the real jj."""

import shutil
from collections.abc import Callable
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
from sculptor.foundation.concurrency_group import ConcurrencyExceptionGroup
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.progress_tracking.progress_tracking import RootProgressHandle
from sculptor.primitives.constants import ANONYMOUS_ORGANIZATION_REFERENCE
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import TaskID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.jj_availability import JjUnavailableError
from sculptor.services.user_config.user_config import get_user_config_instance
from sculptor.services.user_config.user_config import set_user_config_instance
from sculptor.services.workspace_service.environment_manager import (
    default_implementation as environment_manager_default_implementation,
)
from sculptor.services.workspace_service.environment_manager.environments import local_environment
from sculptor.testing.jj_repos import JJ_TEST_USER_EMAIL
from sculptor.testing.jj_repos import JJ_TEST_USER_NAME
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


def test_resuming_a_jj_workspace_re_applies_the_current_snapshot_size_limit(
    jj_binary: JjBinary,
    jj_project: Project,
    test_service_collection: CompleteServiceCollection,
    test_root_concurrency_group: ConcurrencyGroup,
) -> None:
    workspace = _create_jj_workspace(test_service_collection, jj_project, source_branch=None)
    checkout = _start_first_agent(test_service_collection, jj_project, workspace, test_root_concurrency_group)
    set_user_config_instance(get_user_config_instance().model_copy(update={"jj_snapshot_max_new_file_size_mib": 3}))

    resumed_checkout = _start_first_agent(test_service_collection, jj_project, workspace, test_root_concurrency_group)

    assert resumed_checkout == checkout
    limit = run_jj(jj_binary, ("config", "get", "snapshot.max-new-file-size"), cwd=checkout).strip()
    assert limit == str(3 * 1024 * 1024)


def test_startup_forgets_a_deleted_jj_workspace_whose_teardown_never_reached_the_repository(
    jj_binary: JjBinary,
    jj_colocated_repo: JjColocatedRepo,
    jj_project: Project,
    test_service_collection: CompleteServiceCollection,
    test_root_concurrency_group: ConcurrencyGroup,
) -> None:
    """As when Sculptor exits after the soft delete and before the teardown, and the directory is removed later."""
    workspace = _create_jj_workspace(test_service_collection, jj_project, source_branch=None)
    checkout = _start_first_agent(test_service_collection, jj_project, workspace, test_root_concurrency_group)
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        stored_workspace = transaction.get_workspace(workspace.object_id)
        assert stored_workspace is not None
        transaction.upsert_workspace(stored_workspace.evolve(stored_workspace.ref().is_deleted, True))
    shutil.rmtree(checkout.parent)

    test_service_collection.workspace_service.forget_orphaned_jj_workspaces()

    workspace_names = run_jj(jj_binary, ("workspace", "list", "-T", 'name ++ "\\n"'), cwd=jj_colocated_repo.path)
    assert workspace_names.split() == ["default"]


def test_the_orphan_sweep_passes_over_a_project_without_a_local_repository(
    test_service_collection: CompleteServiceCollection,
) -> None:
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        transaction.upsert_project(
            Project(
                object_id=ProjectID(), organization_reference=ANONYMOUS_ORGANIZATION_REFERENCE, name="no repository"
            )
        )

    test_service_collection.workspace_service.forget_orphaned_jj_workspaces()


def _resolve_jj_to(jj_value: str) -> None:
    set_user_config_instance(
        get_user_config_instance().model_copy(update={"dependency_paths": DependencyPaths(jj=jj_value)})
    )


def _uninstall_jj(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A custom jj binary source with no path, so no jj resolves."""
    _resolve_jj_to("CUSTOM")


def _point_jj_at_a_broken_binary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    broken_jj = tmp_path / "broken-jj"
    broken_jj.write_text("#!/bin/sh\necho 'jj: cannot load its libraries' >&2\nexit 1\n")
    broken_jj.chmod(0o755)
    _resolve_jj_to(str(broken_jj))


def _clear_jj_identity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The test identity comes only from the environment; the jj config file is empty."""
    monkeypatch.delenv("JJ_USER")
    monkeypatch.delenv("JJ_EMAIL")


def _fix_jj(jj_binary: JjBinary, monkeypatch: pytest.MonkeyPatch) -> None:
    _resolve_jj_to(str(jj_binary.path))
    monkeypatch.setenv("JJ_USER", JJ_TEST_USER_NAME)
    monkeypatch.setenv("JJ_EMAIL", JJ_TEST_USER_EMAIL)


def _read_latest_operation_id(jj_binary: JjBinary, repo_path: Path) -> str:
    return run_jj(
        jj_binary, ("--ignore-working-copy", "op", "log", "--no-graph", "--limit", "1", "-T", "id"), cwd=repo_path
    )


def _start_agent_while_jj_is_unavailable(
    test_service_collection: CompleteServiceCollection,
    project: Project,
    workspace: Workspace,
    concurrency_group: ConcurrencyGroup,
) -> JjUnavailableError:
    """The error an agent start fails with, unwrapped from its concurrency group as the agent runner unwraps it."""
    with pytest.raises(ConcurrencyExceptionGroup) as raised:
        _start_first_agent(test_service_collection, project, workspace, concurrency_group)
    (error,) = raised.value.exceptions
    assert isinstance(error, JjUnavailableError)
    return error


def _read_environment_id(test_service_collection: CompleteServiceCollection, workspace: Workspace) -> str | None:
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        stored_workspace = transaction.get_workspace(workspace.object_id)
    assert stored_workspace is not None
    return stored_workspace.environment_id


@pytest.mark.parametrize(
    ("make_jj_unavailable", "expected_reason"),
    [
        pytest.param(_uninstall_jj, "jj is not installed", id="uninstalled"),
        pytest.param(_point_jj_at_a_broken_binary, "jj cannot run: jj: cannot load its libraries", id="broken-path"),
        pytest.param(_clear_jj_identity, "jj has no author identity", id="no-identity"),
    ],
)
def test_resuming_a_jj_workspace_while_jj_is_unavailable_says_why_and_changes_nothing_until_jj_is_fixed(
    make_jj_unavailable: Callable[[pytest.MonkeyPatch, Path], None],
    expected_reason: str,
    jj_binary: JjBinary,
    jj_colocated_repo: JjColocatedRepo,
    jj_project: Project,
    test_service_collection: CompleteServiceCollection,
    test_root_concurrency_group: ConcurrencyGroup,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _create_jj_workspace(test_service_collection, jj_project, source_branch=None)
    checkout = _start_first_agent(test_service_collection, jj_project, workspace, test_root_concurrency_group)
    (checkout / "parser.py").write_text("parse = None\n")
    run_jj(jj_binary, ("describe", "-m", "add the parser"), cwd=checkout)
    run_jj(jj_binary, ("bookmark", "create", "feature", "-r", "@"), cwd=checkout)
    operation_before = _read_latest_operation_id(jj_binary, jj_colocated_repo.path)
    environment_id_before = _read_environment_id(test_service_collection, workspace)
    make_jj_unavailable(monkeypatch, tmp_path)

    error = _start_agent_while_jj_is_unavailable(
        test_service_collection, jj_project, workspace, test_root_concurrency_group
    )

    assert str(error).startswith(expected_reason)
    assert (checkout / "parser.py").read_text() == "parse = None\n"
    assert _read_latest_operation_id(jj_binary, jj_colocated_repo.path) == operation_before
    assert _read_environment_id(test_service_collection, workspace) == environment_id_before

    _fix_jj(jj_binary, monkeypatch)
    resumed_checkout = _start_first_agent(test_service_collection, jj_project, workspace, test_root_concurrency_group)

    assert resumed_checkout == checkout
    assert "feature" in run_jj(jj_binary, ("bookmark", "list", "-T", 'name ++ "\\n"'), cwd=checkout).split()


def test_a_first_agent_start_while_jj_is_unavailable_creates_nothing_until_jj_is_fixed(
    jj_binary: JjBinary,
    jj_colocated_repo: JjColocatedRepo,
    jj_project: Project,
    test_service_collection: CompleteServiceCollection,
    test_root_concurrency_group: ConcurrencyGroup,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _create_jj_workspace(test_service_collection, jj_project, source_branch=None)
    _uninstall_jj(monkeypatch, tmp_path)

    error = _start_agent_while_jj_is_unavailable(
        test_service_collection, jj_project, workspace, test_root_concurrency_group
    )

    assert str(error).startswith("jj is not installed")
    assert _read_environment_id(test_service_collection, workspace) is None
    assert list((tmp_path / "workspaces").iterdir()) == []
    workspace_names = run_jj(jj_binary, ("workspace", "list", "-T", 'name ++ "\\n"'), cwd=jj_colocated_repo.path)
    assert workspace_names.split() == ["default"]

    _fix_jj(jj_binary, monkeypatch)
    checkout = _start_first_agent(test_service_collection, jj_project, workspace, test_root_concurrency_group)

    assert (checkout / ".jj" / "repo").is_file()
