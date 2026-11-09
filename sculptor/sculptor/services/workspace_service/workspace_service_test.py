"""Unit tests for WorkspaceService."""

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import PrivateAttr

from sculptor.config.settings import SculptorSettings
from sculptor.config.settings import TEST_LOG_PATH
from sculptor.database.models import Project
from sculptor.database.workspace_enums import DiffStatus
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.git import get_repo_base_path
from sculptor.foundation.progress_tracking.progress_tracking import RootProgressHandle
from sculptor.interfaces.environments.base import Environment
from sculptor.primitives.constants import ANONYMOUS_ORGANIZATION_REFERENCE
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import TaskID
from sculptor.primitives.ids import WorkspaceID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.workspace_service.api import FileAtRefResult
from sculptor.services.workspace_service.api import FileNotFoundAtRefError
from sculptor.services.workspace_service.api import WorkspaceFilesUnavailableError
from sculptor.services.workspace_service.api import WorkspaceNotFoundError
from sculptor.services.workspace_service.default_implementation import DefaultWorkspaceService
from sculptor.services.workspace_service.environment_manager import (
    default_implementation as environment_manager_default_implementation,
)
from sculptor.services.workspace_service.environment_manager.default_implementation import DefaultEnvironmentManager
from sculptor.services.workspace_service.environment_manager.environments import local_environment
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    LocalTerminalManager,
)
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    make_terminal_id,
)
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    register_terminal_manager,
)
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    unregister_terminal_manager,
)
from sculptor.services.workspace_service.vcs.data_types import BranchDeletionPolicy
from sculptor.services.workspace_service.vcs.data_types import CheckoutLocation
from sculptor.services.workspace_service.vcs.git_workspace_vcs import GitWorkspaceVcs
from sculptor.testing.git_snapshot import FullLocalGitRepo
from sculptor.testing.git_snapshot import GitCommitSnapshot
from sculptor.testing.git_snapshot import create_repo_from_snapshot
from sculptor.utils.shutdown import GLOBAL_SHUTDOWN_EVENT

# Running from source, the Sculptor data folder resolves to ``<repo>/.dev_sculptor``
# (see ``get_sculptor_folder``). Workspace creation writes each workspace's
# checkout/state/artifacts there, and diff generation writes per-workspace sync
# artifacts there, neither of which these tests clean up. Left as-is the suite
# accumulates real workspace directories in the repo on every run. The two fixtures
# below redirect every on-disk workspace location into the per-test ``tmp_path``
# (which pytest reclaims automatically) so the suite leaves ``.dev_sculptor`` alone.


@pytest.fixture
def test_settings(database_url: str, tmp_path: Path) -> SculptorSettings:
    """Point the diff-sync artifact dirs at ``tmp_path`` instead of ``.dev_sculptor``.

    Overrides the shared ``test_settings`` fixture (``sculptor/conftest.py``) for this
    module. ``WORKSPACE_SYNC_DIR``/``TASK_SYNC_DIR`` otherwise default under
    ``get_internal_folder()`` (i.e. ``.dev_sculptor/internal/artifacts``), where the
    diff tests would leave a per-workspace artifact directory behind on every run.
    """
    sculptor_artifacts_dir = tmp_path / "sculptor_artifacts"
    return SculptorSettings(
        DATABASE_URL=database_url,
        LOG_PATH=str(TEST_LOG_PATH),
        LOG_LEVEL="TRACE",
        SESSION_TOKEN=None,
        TASK_SYNC_DIR=str(sculptor_artifacts_dir / "task_sync"),
        WORKSPACE_SYNC_DIR=str(sculptor_artifacts_dir / "workspace_sync"),
    )


@pytest.fixture(autouse=True)
def _redirect_workspace_checkouts_to_tmp_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Create workspace checkouts under ``tmp_path`` instead of ``.dev_sculptor/workspaces``.

    ``LOCAL_WORKSPACE_DIR`` captures ``get_workspaces_folder()`` at import time in both
    environment-manager modules, so patching the function alone would not take effect;
    rebind the constant in each module. The creation site and the deletion
    safety-check both read it, so they must stay in agreement.
    """
    workspaces_dir = tmp_path / "workspaces"
    workspaces_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(environment_manager_default_implementation, "LOCAL_WORKSPACE_DIR", workspaces_dir)
    monkeypatch.setattr(local_environment, "LOCAL_WORKSPACE_DIR", workspaces_dir)


@pytest.fixture
def test_project(test_settings: SculptorSettings, test_service_collection: CompleteServiceCollection) -> Project:
    """Create a test project for workspace tests."""
    project_path: str | Path | None = os.getenv("PROJECT_PATH")
    if isinstance(project_path, str):
        project_path = Path(project_path)
    if not project_path:
        project_path = get_repo_base_path()
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        project = test_service_collection.project_service.initialize_project(
            project_path=project_path,
            organization_reference=ANONYMOUS_ORGANIZATION_REFERENCE,
            transaction=transaction,
        )
        test_service_collection.project_service.activate_project(project)
    assert project is not None
    return project


def _create_isolated_git_repo(path: Path, concurrency_group: ConcurrencyGroup) -> Path:
    """Create a minimal git repo at the given path with one commit."""
    repo = create_repo_from_snapshot(
        FullLocalGitRepo(
            git_user_email="test@test.com",
            git_user_name="Test",
            git_branch="main",
            main_history=(
                GitCommitSnapshot(
                    contents_by_path={"README.md": "test"},
                    commit_message="initial",
                    commit_time="2024-01-01T00:00:00",
                ),
            ),
        ),
        destination_path=path,
        concurrency_group=concurrency_group,
    )
    return repo.base_path


# Workspace CRUD operations


def test_create_workspace_in_place(
    test_service_collection: CompleteServiceCollection,
    test_project: Project,
) -> None:
    """Test creating an IN_PLACE workspace."""
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        workspace = test_service_collection.workspace_service.create_workspace(
            project=test_project,
            initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
            source_branch=None,
            requested_branch_name=None,
            description="Test workspace",
            transaction=transaction,
        )

    assert workspace is not None
    assert workspace.project_id == test_project.object_id
    assert workspace.initialization_strategy == WorkspaceInitializationStrategy.IN_PLACE
    assert workspace.source_branch is None
    assert workspace.description == "Test workspace"
    assert workspace.environment_id is None  # Not yet created
    assert not workspace.is_deleted


def test_create_workspace_clone(
    test_service_collection: CompleteServiceCollection,
    test_project: Project,
) -> None:
    """Test creating a CLONE workspace."""
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        workspace = test_service_collection.workspace_service.create_workspace(
            project=test_project,
            initialization_strategy=WorkspaceInitializationStrategy.CLONE,
            source_branch="feature-branch",
            requested_branch_name=None,
            description="Clone workspace",
            transaction=transaction,
        )

    assert workspace is not None
    assert workspace.initialization_strategy == WorkspaceInitializationStrategy.CLONE
    assert workspace.source_branch == "feature-branch"


def test_create_workspace_generates_description_without_prefix(
    test_service_collection: CompleteServiceCollection,
    test_project: Project,
) -> None:
    """Test that workspace description is auto-generated without a 'Workspace' prefix."""
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        workspace = test_service_collection.workspace_service.create_workspace(
            project=test_project,
            initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
            source_branch=None,
            requested_branch_name=None,
            description=None,  # Should be auto-generated
            transaction=transaction,
        )

    assert workspace.description is not None
    assert len(workspace.description) == 8
    assert not workspace.description.startswith("Workspace")


def test_delete_workspace(
    test_service_collection: CompleteServiceCollection,
    test_project: Project,
) -> None:
    """Test deleting a workspace."""
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        workspace = test_service_collection.workspace_service.create_workspace(
            project=test_project,
            initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
            source_branch=None,
            requested_branch_name=None,
            description="To be deleted",
            transaction=transaction,
        )
        workspace_id = workspace.object_id

    # Verify workspace exists before deletion
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        existing_workspace = transaction.get_workspace(workspace_id)
        assert existing_workspace is not None

    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        test_service_collection.workspace_service.delete_workspace(workspace_id, transaction)

    # Verify workspace is no longer findable (deleted workspaces are filtered out)
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        deleted_workspace = transaction.get_workspace(workspace_id)
        assert deleted_workspace is None


def test_delete_workspace_not_found(
    test_service_collection: CompleteServiceCollection,
) -> None:
    """Test deleting a non-existent workspace raises error."""
    fake_workspace_id = WorkspaceID()

    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        with pytest.raises(WorkspaceNotFoundError):
            test_service_collection.workspace_service.delete_workspace(fake_workspace_id, transaction)


def test_workspace_lookup_via_transaction(
    test_service_collection: CompleteServiceCollection,
    test_project: Project,
) -> None:
    """Test that workspaces can be looked up via transaction.get_workspace().

    This verifies the design that workspace lookups should use the transaction
    directly, not WorkspaceService methods.
    """
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        workspace = test_service_collection.workspace_service.create_workspace(
            project=test_project,
            initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
            source_branch=None,
            requested_branch_name=None,
            description="Lookup test",
            transaction=transaction,
        )
        workspace_id = workspace.object_id

    # Look up workspace via transaction (not workspace_service)
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        found_workspace = transaction.get_workspace(workspace_id)

    assert found_workspace is not None
    assert found_workspace.object_id == workspace_id
    assert found_workspace.description == "Lookup test"


def test_workspace_list_via_transaction(
    test_service_collection: CompleteServiceCollection,
    test_project: Project,
) -> None:
    """Test that workspaces can be listed via transaction.get_workspaces().

    This verifies the design that workspace lookups should use the transaction
    directly, not WorkspaceService methods.
    """
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        workspace1 = test_service_collection.workspace_service.create_workspace(
            project=test_project,
            initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
            source_branch=None,
            requested_branch_name=None,
            description="Workspace 1",
            transaction=transaction,
        )
        workspace2 = test_service_collection.workspace_service.create_workspace(
            project=test_project,
            initialization_strategy=WorkspaceInitializationStrategy.CLONE,
            source_branch="main",
            requested_branch_name=None,
            description="Workspace 2",
            transaction=transaction,
        )

    # List workspaces via transaction (not workspace_service)
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        workspaces = transaction.get_workspaces(project_id=test_project.object_id)

    workspace_ids = {w.object_id for w in workspaces}
    assert workspace1.object_id in workspace_ids
    assert workspace2.object_id in workspace_ids


# Workspace diff operations


def test_create_workspace_captures_source_git_hash(
    test_service_collection: CompleteServiceCollection,
    test_project: Project,
) -> None:
    """Test that creating a workspace captures the current git hash."""
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        workspace = test_service_collection.workspace_service.create_workspace(
            project=test_project,
            initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
            source_branch=None,
            requested_branch_name=None,
            description="Test workspace",
            transaction=transaction,
        )

    # source_git_hash should be captured (assuming we're in a git repo)
    source_git_hash = workspace.source_git_hash
    assert source_git_hash is not None
    # Git hash should be a valid-looking 40-character hex string
    assert len(source_git_hash) == 40
    assert all(c in "0123456789abcdef" for c in source_git_hash)


def test_get_workspace_diff_generates_on_demand_when_artifact_missing(
    test_service_collection: CompleteServiceCollection,
    test_project: Project,
) -> None:
    """Test that get_workspace_diff generates the diff on-demand when the artifact is missing.

    This supports lazy diff loading: agent startup marks the diff as READY
    without generating the artifact, and get_workspace_diff generates it
    when the frontend fetches it.
    """
    # Create workspace without letting the callback run
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        workspace = test_service_collection.workspace_service.create_workspace(
            project=test_project,
            initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
            source_branch=None,
            requested_branch_name=None,
            description="Test workspace",
            transaction=transaction,
        )
        workspace_id = workspace.object_id

    # Manually remove any generated diff to simulate the lazy startup path
    assert isinstance(test_service_collection.workspace_service, DefaultWorkspaceService)
    artifact_dir = test_service_collection.workspace_service.workspace_sync_dir / str(workspace_id)
    if artifact_dir.exists():
        shutil.rmtree(artifact_dir)

    # Get diff should generate on-demand and return a valid artifact
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        diff = test_service_collection.workspace_service.get_workspace_diff(
            workspace_id, transaction, force_refresh=False
        )

    assert diff is not None


def test_refresh_workspace_diff_creates_diff_artifact(
    test_service_collection: CompleteServiceCollection,
    test_project: Project,
) -> None:
    """Test that refresh_workspace_diff creates a diff artifact and updates workspace status."""
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        workspace = test_service_collection.workspace_service.create_workspace(
            project=test_project,
            initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
            source_branch=None,
            requested_branch_name=None,
            description="Test workspace",
            transaction=transaction,
        )
        workspace_id = workspace.object_id

    test_service_collection.workspace_service.refresh_workspace_diff(workspace_id)

    # Verify workspace has diff_status=READY and diff_updated_at set
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        updated_workspace = transaction.get_workspace(workspace_id)
    assert updated_workspace is not None
    assert updated_workspace.diff_status == DiffStatus.READY
    assert updated_workspace.diff_updated_at is not None

    # Get the diff and verify it exists
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        diff = test_service_collection.workspace_service.get_workspace_diff(
            workspace_id, transaction, force_refresh=False
        )

    assert diff is not None
    assert hasattr(diff, "uncommitted_diff")


def test_get_workspace_diff_with_force_refresh(
    test_service_collection: CompleteServiceCollection,
    test_project: Project,
) -> None:
    """Test that force_refresh=True regenerates the diff."""
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        workspace = test_service_collection.workspace_service.create_workspace(
            project=test_project,
            initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
            source_branch=None,
            requested_branch_name=None,
            description="Test workspace",
            transaction=transaction,
        )
        workspace_id = workspace.object_id

    # Get diff with force_refresh
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        diff = test_service_collection.workspace_service.get_workspace_diff(
            workspace_id, transaction, force_refresh=True
        )

    assert diff is not None


def test_maybe_refresh_workspace_diff_always_refreshes(
    test_service_collection: CompleteServiceCollection,
    test_project: Project,
) -> None:
    """Test that maybe_refresh_workspace_diff refreshes the diff (always refreshes for now)."""
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        workspace = test_service_collection.workspace_service.create_workspace(
            project=test_project,
            initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
            source_branch=None,
            requested_branch_name=None,
            description="Test workspace",
            transaction=transaction,
        )
        workspace_id = workspace.object_id

    test_service_collection.workspace_service.maybe_refresh_workspace_diff(workspace_id)

    # Verify workspace has diff_status=READY and diff_updated_at set
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        updated_workspace = transaction.get_workspace(workspace_id)
    assert updated_workspace is not None
    assert updated_workspace.diff_status == DiffStatus.READY
    assert updated_workspace.diff_updated_at is not None


# Workspace git operations


def test_diff_not_found_raises_error(
    test_service_collection: CompleteServiceCollection,
) -> None:
    """Test that operations on non-existent workspace raise WorkspaceNotFoundError."""
    fake_workspace_id = WorkspaceID()

    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        with pytest.raises(WorkspaceNotFoundError):
            test_service_collection.workspace_service.get_workspace_diff(
                fake_workspace_id, transaction, force_refresh=False
            )


# Workspace diff isolation


def test_two_workspaces_have_separate_diffs_visible_to_all_their_agents(
    test_service_collection: CompleteServiceCollection,
    test_root_concurrency_group: ConcurrencyGroup,
    tmp_path: Path,
) -> None:
    """Two workspaces backed by different repos should produce independent diffs.

    For each workspace we launch two agents (via agent_environment_context).
    One agent makes a file change; then we refresh the diff.  All four agents
    (two per workspace) should see the diff that corresponds to *their*
    workspace, not the other one.
    """
    # --- Set up two isolated repos, projects, and workspaces ---
    repo_a = _create_isolated_git_repo(tmp_path / "repo_a", test_root_concurrency_group)
    repo_b = _create_isolated_git_repo(tmp_path / "repo_b", test_root_concurrency_group)

    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        project_a = test_service_collection.project_service.initialize_project(
            project_path=repo_a,
            organization_reference=ANONYMOUS_ORGANIZATION_REFERENCE,
            transaction=transaction,
        )
        test_service_collection.project_service.activate_project(project_a)
        workspace_a = test_service_collection.workspace_service.create_workspace(
            project=project_a,
            initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
            source_branch=None,
            requested_branch_name=None,
            description="Workspace A",
            transaction=transaction,
        )

    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        project_b = test_service_collection.project_service.initialize_project(
            project_path=repo_b,
            organization_reference=ANONYMOUS_ORGANIZATION_REFERENCE,
            transaction=transaction,
        )
        test_service_collection.project_service.activate_project(project_b)
        workspace_b = test_service_collection.workspace_service.create_workspace(
            project=project_b,
            initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
            source_branch=None,
            requested_branch_name=None,
            description="Workspace B",
            transaction=transaction,
        )

    ws_id_a = workspace_a.object_id
    ws_id_b = workspace_b.object_id

    # --- Create a file unique to each repo (simulating agent work) ---
    # For IN_PLACE workspaces the diff is computed against the project repo,
    # so we write directly to the repo path.
    (repo_a / "only_in_a.txt").write_text("workspace A content")
    (repo_b / "only_in_b.txt").write_text("workspace B content")

    # --- Refresh diffs for both workspaces ---
    test_service_collection.workspace_service.refresh_workspace_diff(ws_id_a)
    test_service_collection.workspace_service.refresh_workspace_diff(ws_id_b)

    # --- Read diffs as each of four agents would see them ---
    # Two independent reads per workspace simulate two agents reading the
    # same workspace's diff (they should get identical results).
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        diff_a_read1 = test_service_collection.workspace_service.get_workspace_diff(
            ws_id_a, transaction, force_refresh=False
        )
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        diff_a_read2 = test_service_collection.workspace_service.get_workspace_diff(
            ws_id_a, transaction, force_refresh=False
        )
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        diff_b_read1 = test_service_collection.workspace_service.get_workspace_diff(
            ws_id_b, transaction, force_refresh=False
        )
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        diff_b_read2 = test_service_collection.workspace_service.get_workspace_diff(
            ws_id_b, transaction, force_refresh=False
        )

    # --- Assertions ---
    assert diff_a_read1 is not None
    assert diff_a_read2 is not None
    assert diff_b_read1 is not None
    assert diff_b_read2 is not None

    # Both reads of workspace A return the same diff (agents share the workspace diff)
    assert diff_a_read1 == diff_a_read2

    # Both reads of workspace B return the same diff
    assert diff_b_read1 == diff_b_read2

    # Workspace A's diff mentions only_in_a.txt, not only_in_b.txt
    assert "only_in_a.txt" in diff_a_read1.uncommitted_diff
    assert "only_in_b.txt" not in diff_a_read1.uncommitted_diff

    # Workspace B's diff mentions only_in_b.txt, not only_in_a.txt
    assert "only_in_b.txt" in diff_b_read1.uncommitted_diff
    assert "only_in_a.txt" not in diff_b_read1.uncommitted_diff


# Workspace environment deletion


def test_delete_workspace_removes_environment_directory(
    test_service_collection: CompleteServiceCollection,
    test_project: Project,
    test_root_concurrency_group: ConcurrencyGroup,
) -> None:
    """Deleting a workspace with an environment should remove its directory on disk.

    The environment directory is deleted on a background thread scheduled by a
    post-commit callback (SCU-1374), so the request thread is not blocked on the
    rmtree.  This test verifies the full lifecycle: create workspace -> create
    environment -> delete workspace -> directory eventually gone.
    """
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        workspace = test_service_collection.workspace_service.create_workspace(
            project=test_project,
            initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
            source_branch=None,
            requested_branch_name=None,
            description="Env deletion test",
            transaction=transaction,
        )
    workspace_id = workspace.object_id

    # Create the environment via agent_environment_context
    with test_root_concurrency_group.make_concurrency_group("env_test") as concurrency_group:
        with test_service_collection.workspace_service.agent_environment_context(
            project=test_project,
            workspace_id=workspace_id,
            task_id=TaskID(),
            concurrency_group=concurrency_group,
            root_progress_handle=RootProgressHandle(),
            shutdown_event=GLOBAL_SHUTDOWN_EVENT,
        ):
            pass  # Just need the environment created

    # Verify environment directory was created
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        workspace_with_env = transaction.get_workspace(workspace_id)
    assert workspace_with_env is not None
    assert workspace_with_env.environment_id is not None
    env_path = Path(workspace_with_env.environment_id)
    assert env_path.exists(), f"Environment directory should exist at {env_path}"

    # Delete the workspace (a post-commit callback schedules the directory
    # removal on a background thread)
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        test_service_collection.workspace_service.delete_workspace(workspace_id, transaction)

    # The directory is removed asynchronously, so poll until it is gone.
    deadline = time.monotonic() + 10.0
    while env_path.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not env_path.exists(), f"Environment directory should be deleted at {env_path}"


class _ThreadRecordingEnvironmentManager(DefaultEnvironmentManager):
    """Environment manager that records which thread runs the teardown.

    Used to prove that the slow filesystem teardown is offloaded off the
    request thread when a workspace is deleted.
    """

    _teardown_threads: list[threading.Thread] = PrivateAttr(default_factory=list)
    _teardown_done: threading.Event = PrivateAttr(default_factory=threading.Event)

    def delete_environment(self, environment_id: str) -> None:
        self._teardown_threads.append(threading.current_thread())
        super().delete_environment(environment_id)
        self._teardown_done.set()


def test_delete_workspace_offloads_environment_teardown_off_request_thread(
    test_service_collection: CompleteServiceCollection,
    test_project: Project,
    test_root_concurrency_group: ConcurrencyGroup,
) -> None:
    """Environment teardown must not run on the request thread (SCU-1374).

    Deleting a workspace removes its on-disk environment with ``shutil.rmtree``,
    which can take many seconds for a real worktree (node_modules, venvs, build
    artifacts). If that teardown runs synchronously in the request's post-commit
    hook, the DELETE request occupies its server worker thread for the entire
    rmtree; rapidly deleting several workspaces then exhausts the connection /
    threadpool limit and the app starts dropping requests (the reported symptom).
    The teardown must therefore be offloaded to a background thread so the
    request returns promptly.
    """
    workspace_service = test_service_collection.workspace_service
    assert isinstance(workspace_service, DefaultWorkspaceService)

    # Create a workspace with a real on-disk environment.
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        workspace = workspace_service.create_workspace(
            project=test_project,
            initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
            source_branch=None,
            requested_branch_name=None,
            description="Teardown offload test",
            transaction=transaction,
        )
    workspace_id = workspace.object_id

    with test_root_concurrency_group.make_concurrency_group("env_test") as concurrency_group:
        with workspace_service.agent_environment_context(
            project=test_project,
            workspace_id=workspace_id,
            task_id=TaskID(),
            concurrency_group=concurrency_group,
            root_progress_handle=RootProgressHandle(),
            shutdown_event=GLOBAL_SHUTDOWN_EVENT,
        ):
            pass  # Just need the environment created

    # Swap in an environment manager that records the thread the teardown runs on.
    existing_manager = workspace_service.environment_manager
    assert isinstance(existing_manager, DefaultEnvironmentManager)
    recording_manager = _ThreadRecordingEnvironmentManager(
        data_model_service=existing_manager.data_model_service,
    )
    workspace_service.environment_manager = recording_manager

    request_thread = threading.current_thread()

    # Delete the workspace on this (the request) thread.
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        workspace_service.delete_workspace(workspace_id, transaction)

    # The soft-delete is committed synchronously: the workspace is already gone.
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        assert transaction.get_workspace(workspace_id) is None

    # The slow filesystem teardown must have run on a *different* thread, proving
    # the request was not blocked waiting for it.
    assert recording_manager._teardown_done.wait(timeout=10.0), "environment teardown never ran"
    teardown_thread = recording_manager._teardown_threads[0]
    assert teardown_thread is not request_thread, (
        "environment teardown ran on the request thread; it must run on a background thread (SCU-1374)"
    )


def test_delete_worktree_workspace_removes_the_worktree_and_its_merged_branch(
    test_service_collection: CompleteServiceCollection,
    test_root_concurrency_group: ConcurrencyGroup,
    tmp_path: Path,
) -> None:
    workspace_service = test_service_collection.workspace_service
    assert isinstance(workspace_service, DefaultWorkspaceService)
    repo_path = _create_isolated_git_repo(tmp_path / "repo", test_root_concurrency_group)
    branch_name = f"worktree-{uuid4().hex[:8]}"
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        initialized_project = test_service_collection.project_service.initialize_project(
            project_path=repo_path,
            organization_reference=ANONYMOUS_ORGANIZATION_REFERENCE,
            transaction=transaction,
        )
        test_service_collection.project_service.activate_project(initialized_project)
        # No setup command, so no background setup process outlives the test.
        project = transaction.update_project_fields(initialized_project.object_id, workspace_setup_command="")
        assert project is not None
        workspace = workspace_service.create_workspace(
            project=project,
            initialization_strategy=WorkspaceInitializationStrategy.WORKTREE,
            source_branch="main",
            requested_branch_name=branch_name,
            description="Worktree deletion",
            transaction=transaction,
        )
    with test_root_concurrency_group.make_concurrency_group("env_test") as concurrency_group:
        with workspace_service.agent_environment_context(
            project=project,
            workspace_id=workspace.object_id,
            task_id=TaskID(),
            concurrency_group=concurrency_group,
            root_progress_handle=RootProgressHandle(),
            shutdown_event=GLOBAL_SHUTDOWN_EVENT,
        ):
            pass
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        workspace_with_environment = transaction.get_workspace(workspace.object_id)
    assert workspace_with_environment is not None and workspace_with_environment.environment_id is not None
    checkout_path = Path(workspace_with_environment.environment_id) / "code"
    assert (checkout_path / ".git").is_file()

    existing_manager = workspace_service.environment_manager
    assert isinstance(existing_manager, DefaultEnvironmentManager)
    recording_manager = _ThreadRecordingEnvironmentManager(data_model_service=existing_manager.data_model_service)
    workspace_service.environment_manager = recording_manager
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        workspace_service.delete_workspace(workspace.object_id, transaction)
    assert recording_manager._teardown_done.wait(timeout=10.0), "environment teardown never ran"

    worktree_list = subprocess.run(
        ["git", "-C", str(repo_path), "worktree", "list", "--porcelain"], check=True, capture_output=True, text=True
    ).stdout
    branch_list = subprocess.run(
        ["git", "-C", str(repo_path), "branch", "--list", branch_name], check=True, capture_output=True, text=True
    ).stdout
    assert str(checkout_path) not in worktree_list
    assert branch_list == ""


class _ResumeCountingEnvironmentManager(DefaultEnvironmentManager):
    """Environment manager that counts `resume_environment` calls."""

    _resume_count: int = PrivateAttr(default=0)

    def resume_environment(
        self,
        environment_id: str,
        project_path: Path,
        project_id: ProjectID,
        concurrency_group: ConcurrencyGroup,
        initialization_strategy: WorkspaceInitializationStrategy = WorkspaceInitializationStrategy.IN_PLACE,
        env_var_override: bool = False,
        sculptor_folder: Path | None = None,
    ) -> Environment:
        self._resume_count += 1
        return super().resume_environment(
            environment_id,
            project_path,
            project_id,
            concurrency_group,
            initialization_strategy,
            env_var_override,
            sculptor_folder,
        )


@pytest.mark.parametrize(
    "initialization_strategy", [WorkspaceInitializationStrategy.CLONE, WorkspaceInitializationStrategy.WORKTREE]
)
def test_get_workspace_working_directory_finds_the_checkout_without_resuming_the_environment(
    test_service_collection: CompleteServiceCollection,
    test_project: Project,
    tmp_path: Path,
    initialization_strategy: WorkspaceInitializationStrategy,
) -> None:
    """The branch poller calls this for every workspace on every cycle, so it must not resume environments."""
    workspace_service = test_service_collection.workspace_service
    assert isinstance(workspace_service, DefaultWorkspaceService)
    existing_manager = workspace_service.environment_manager
    assert isinstance(existing_manager, DefaultEnvironmentManager)
    counting_manager = _ResumeCountingEnvironmentManager(data_model_service=existing_manager.data_model_service)
    workspace_service.environment_manager = counting_manager

    environment_dir = tmp_path / f"environment-{uuid4().hex}"
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        workspace = workspace_service.create_workspace(
            project=test_project,
            initialization_strategy=initialization_strategy,
            source_branch="main",
            requested_branch_name=f"working-dir-{uuid4().hex[:8]}",
            description="Working directory lookup",
            transaction=transaction,
        )
        workspace = transaction.update_workspace_fields(workspace.object_id, environment_id=str(environment_dir))
    assert workspace is not None

    working_directory = workspace_service.get_workspace_working_directory(workspace)

    assert working_directory == environment_dir / "code"
    assert counting_manager._resume_count == 0


def _wait_for_dead(pid: int, timeout: float = 1.0) -> bool:
    """Return True once ``os.kill(pid, 0)`` raises ProcessLookupError within ``timeout``."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.005)


@pytest.mark.skipif(sys.platform == "win32", reason="real pty teardown is POSIX-only")
def test_delete_worktree_workspace_stops_terminals_before_removing_worktree(
    test_service_collection: CompleteServiceCollection,
    test_project: Project,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A workspace terminal's child process must be killed before its worktree is removed.

    Regression test for SCU-1424: deleting a WORKTREE workspace removed the
    worktree (which deletes the ``<environment_id>/code`` checkout a
    running terminal uses as its working directory) *before*
    ``stop_terminals_for_environment``.  A process running in the terminal then
    had its working directory yanked out from under it, producing the messy
    "Electron quit unexpectedly" / JavaScript-error shutdown described in the
    ticket.  The clean quit path and ``LocalEnvironment.destroy`` both stop
    terminals first, so deletion must do the same.

    This is a backend test because the messy crash happens in a separate child
    process and depends on OS-level process/filesystem timing — it is not
    observable through the Sculptor UI that Playwright drives (the workspace
    disappears either way).  We drive the real ``delete_workspace`` flow with a
    real pty and assert the terminal child is already dead at the moment the
    worktree-removal step runs.
    """
    # Create a WORKTREE workspace so the worktree-removal step of the deletion
    # callback runs.
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        workspace = test_service_collection.workspace_service.create_workspace(
            project=test_project,
            initialization_strategy=WorkspaceInitializationStrategy.WORKTREE,
            source_branch="main",
            requested_branch_name=f"scu-1424-{uuid4().hex[:8]}",
            description="Worktree delete ordering",
            transaction=transaction,
        )
        workspace_id = workspace.object_id

    # Point the workspace at a real on-disk environment directory containing the
    # `code/` worktree checkout that the terminal uses as its working directory.
    environment_dir = tmp_path / "environment"
    working_directory = environment_dir / "code"
    working_directory.mkdir(parents=True)
    environment_id = str(environment_dir)
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        transaction.update_workspace_fields(workspace_id, environment_id=environment_id)

    shell_dead_when_worktree_removed: list[bool] = []

    with ConcurrencyGroup(name="scu1424-terminal") as concurrency_group:
        terminal_id = make_terminal_id(environment_id, 0)
        manager = LocalTerminalManager(
            environment_id=environment_id,
            terminal_index=0,
            workspace_path=environment_dir,
            working_directory=working_directory,
            concurrency_group=concurrency_group,
        )
        manager.start()
        register_terminal_manager(terminal_id, manager)
        try:
            assert manager._pty_process is not None
            helper = manager._pty_process._helper
            assert helper is not None
            shell_pid = helper.shell_pid
            assert shell_pid > 0
            os.kill(shell_pid, 0)  # the shell is alive right now

            # Spy on the worktree-removal step to record whether the terminal's
            # child process is already gone when it runs.  We deliberately skip
            # the real git worktree removal — its git behaviour is irrelevant to
            # the ordering under test.
            def _record_terminal_liveness(
                self: GitWorkspaceVcs,
                location: CheckoutLocation,
                created_ref_name: str | None,
                deletion_policy: BranchDeletionPolicy,
            ) -> None:
                shell_dead_when_worktree_removed.append(_wait_for_dead(shell_pid))

            monkeypatch.setattr(GitWorkspaceVcs, "remove_checkout", _record_terminal_liveness)

            # Delete the workspace.  The post-commit callback fires when the
            # transaction commits on block exit, but it offloads the actual
            # teardown (terminal shutdown + worktree removal + rmtree) to a
            # background thread (SCU-1374), so the worktree-removal spy runs
            # asynchronously rather than inline.
            with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
                test_service_collection.workspace_service.delete_workspace(workspace_id, transaction)

            # Wait for the background teardown to reach the worktree-removal step
            # and record its observation before asserting on it.
            deadline = time.monotonic() + 10.0
            while not shell_dead_when_worktree_removed and time.monotonic() < deadline:
                time.sleep(0.01)

            assert shell_dead_when_worktree_removed == [True], (
                "terminal child still alive when worktree removed; deletion must stop terminals first (SCU-1424)"
            )
            assert _wait_for_dead(shell_pid), f"terminal shell pid {shell_pid} still alive after delete"
        finally:
            try:
                manager.stop()
            except BaseException:
                pass
            unregister_terminal_manager(terminal_id)


# Concurrent environment setup


def test_concurrent_setup_creates_single_environment(
    test_service_collection: CompleteServiceCollection,
    test_project: Project,
    test_root_concurrency_group: ConcurrencyGroup,
) -> None:
    """Two concurrent agent_environment_context calls for the same workspace
    should result in a single environment being created, not two.

    This verifies the per-workspace lock prevents the data race where both
    threads see environment_id=None and each creates a separate environment.
    """
    # Create a workspace without an environment yet
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        workspace = test_service_collection.workspace_service.create_workspace(
            project=test_project,
            initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
            source_branch=None,
            requested_branch_name=None,
            description="Concurrent test workspace",
            transaction=transaction,
        )

    workspace_id = workspace.object_id
    environment_ids: list[str] = []
    errors: list[Exception] = []
    barrier = threading.Barrier(2)

    def setup_environment(task_index: int) -> None:
        try:
            with test_root_concurrency_group.make_concurrency_group(f"task_{task_index}") as concurrency_group:
                # Synchronize both threads to maximize race window
                barrier.wait(timeout=5)
                with test_service_collection.workspace_service.agent_environment_context(
                    project=test_project,
                    workspace_id=workspace_id,
                    task_id=TaskID(),
                    concurrency_group=concurrency_group,
                    root_progress_handle=RootProgressHandle(),
                    shutdown_event=GLOBAL_SHUTDOWN_EVENT,
                ) as agent_env:
                    environment_ids.append(agent_env.get_root_path().as_posix())
        except Exception as e:
            errors.append(e)

    thread1 = threading.Thread(target=setup_environment, args=(0,))
    thread2 = threading.Thread(target=setup_environment, args=(1,))
    thread1.start()
    thread2.start()
    thread1.join(timeout=30)
    thread2.join(timeout=30)

    assert not errors, f"Threads raised errors: {errors}"
    assert len(environment_ids) == 2
    # Both threads should have gotten the same environment (same workspace path)
    assert environment_ids[0] == environment_ids[1], (
        f"Expected same environment for both tasks, got {environment_ids[0]} and {environment_ids[1]}"
    )

    # Verify the workspace has a single environment_id in the database
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        final_workspace = transaction.get_workspace(workspace_id)
    assert final_workspace is not None
    assert final_workspace.environment_id is not None


# Target branch diff


def _create_repo_with_origin_and_feature_branch(
    tmp_path: Path,
    concurrency_group: ConcurrencyGroup,
) -> Path:
    """Create a git repo on a feature branch with an origin remote.

    The repo has:
    - A ``main`` branch with one initial commit (pushed to a bare ``origin``).
    - A ``feature`` branch checked out with one new commit adding ``new_file.txt``.
    """
    repo_path = _create_isolated_git_repo(tmp_path / "repo", concurrency_group)

    # Create a bare clone to act as origin
    origin_path = tmp_path / "origin.git"
    subprocess.run(
        ["git", "clone", "--bare", str(repo_path), str(origin_path)],
        check=True,
        capture_output=True,
    )

    # Add origin remote and fetch so origin/main exists
    subprocess.run(["git", "-C", str(repo_path), "remote", "add", "origin", str(origin_path)], check=True)
    subprocess.run(["git", "-C", str(repo_path), "fetch", "origin"], check=True, capture_output=True)

    # Create feature branch with a new file
    subprocess.run(["git", "-C", str(repo_path), "checkout", "-b", "feature"], check=True, capture_output=True)
    (repo_path / "new_file.txt").write_text("new content")
    subprocess.run(["git", "-C", str(repo_path), "add", "new_file.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repo_path), "commit", "-m", "Add new file"],
        check=True,
        capture_output=True,
    )

    return repo_path


def test_create_workspace_auto_resolves_target_branch_with_origin(
    test_service_collection: CompleteServiceCollection,
    test_root_concurrency_group: ConcurrencyGroup,
    tmp_path: Path,
) -> None:
    """Workspace creation should auto-resolve target_branch when origin/main exists."""
    repo_path = _create_repo_with_origin_and_feature_branch(tmp_path, test_root_concurrency_group)

    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        project = test_service_collection.project_service.initialize_project(
            project_path=repo_path,
            organization_reference=ANONYMOUS_ORGANIZATION_REFERENCE,
            transaction=transaction,
        )
        test_service_collection.project_service.activate_project(project)
        workspace = test_service_collection.workspace_service.create_workspace(
            project=project,
            initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
            source_branch=None,
            requested_branch_name=None,
            description="Test workspace",
            transaction=transaction,
        )

    assert workspace.target_branch == "origin/main"


def test_create_workspace_resolves_target_branch_to_what_origin_head_points_at(
    test_service_collection: CompleteServiceCollection,
    test_root_concurrency_group: ConcurrencyGroup,
    tmp_path: Path,
) -> None:
    repo_path = _create_repo_with_origin_and_feature_branch(tmp_path, test_root_concurrency_group)
    subprocess.run(["git", "-C", str(repo_path), "push", "origin", "feature"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo_path), "remote", "set-head", "origin", "feature"], check=True)

    workspace_id = _create_in_place_workspace(test_service_collection, repo_path)

    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        workspace = transaction.get_workspace(workspace_id)
    assert workspace is not None
    assert workspace.target_branch == "origin/feature"
    assert workspace.source_git_hash == _read_head_commit(repo_path)


def test_create_workspace_uses_explicit_target_branch_over_auto_resolution(
    test_service_collection: CompleteServiceCollection,
    test_root_concurrency_group: ConcurrencyGroup,
    tmp_path: Path,
) -> None:
    """An explicit target_branch should override the auto-resolved default."""
    repo_path = _create_repo_with_origin_and_feature_branch(tmp_path, test_root_concurrency_group)

    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        project = test_service_collection.project_service.initialize_project(
            project_path=repo_path,
            organization_reference=ANONYMOUS_ORGANIZATION_REFERENCE,
            transaction=transaction,
        )
        test_service_collection.project_service.activate_project(project)
        workspace = test_service_collection.workspace_service.create_workspace(
            project=project,
            initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
            source_branch=None,
            requested_branch_name=None,
            description="Test workspace",
            transaction=transaction,
            target_branch="feature",
        )

    # "feature" wins even though auto-resolution would have picked "origin/main".
    assert workspace.target_branch == "feature"


def test_create_workspace_target_branch_falls_back_to_local_main_without_remote(
    test_service_collection: CompleteServiceCollection,
    test_root_concurrency_group: ConcurrencyGroup,
    tmp_path: Path,
) -> None:
    """IN_PLACE workspace on a local-only repo should resolve target_branch to the bare local default branch.

    IN_PLACE workspaces share .git with the user's repo, so the bare branch
    name (``main``/``master``) resolves directly.
    """
    repo_path = _create_isolated_git_repo(tmp_path / "no_remote_repo", test_root_concurrency_group)

    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        project = test_service_collection.project_service.initialize_project(
            project_path=repo_path,
            organization_reference=ANONYMOUS_ORGANIZATION_REFERENCE,
            transaction=transaction,
        )
        test_service_collection.project_service.activate_project(project)
        workspace = test_service_collection.workspace_service.create_workspace(
            project=project,
            initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
            source_branch=None,
            requested_branch_name=None,
            description="No remote workspace",
            transaction=transaction,
        )

    assert workspace.target_branch == "main"


def test_create_workspace_clone_falls_back_to_origin_main(
    test_service_collection: CompleteServiceCollection,
    test_root_concurrency_group: ConcurrencyGroup,
    tmp_path: Path,
) -> None:
    """CLONE workspace without origin should resolve target_branch to origin/main.

    When the source has no remotes, clone_strategy creates a synthetic
    ``origin`` remote and seeds ``refs/remotes/origin/<branch>`` from the
    source's local branches, so the fallback target branch lives under
    ``origin/*`` in the clone.
    """
    repo_path = _create_isolated_git_repo(tmp_path / "clone_no_origin", test_root_concurrency_group)

    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        project = test_service_collection.project_service.initialize_project(
            project_path=repo_path,
            organization_reference=ANONYMOUS_ORGANIZATION_REFERENCE,
            transaction=transaction,
        )
        test_service_collection.project_service.activate_project(project)
        workspace = test_service_collection.workspace_service.create_workspace(
            project=project,
            initialization_strategy=WorkspaceInitializationStrategy.CLONE,
            source_branch=None,
            requested_branch_name=None,
            description="Clone no origin",
            transaction=transaction,
        )

    assert workspace.target_branch == "origin/main"


def test_target_branch_diff_uses_auto_resolved_branch(
    test_service_collection: CompleteServiceCollection,
    test_root_concurrency_group: ConcurrencyGroup,
    tmp_path: Path,
) -> None:
    """Target branch diff should use the auto-resolved target_branch."""
    repo_path = _create_repo_with_origin_and_feature_branch(tmp_path, test_root_concurrency_group)

    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        project = test_service_collection.project_service.initialize_project(
            project_path=repo_path,
            organization_reference=ANONYMOUS_ORGANIZATION_REFERENCE,
            transaction=transaction,
        )
        test_service_collection.project_service.activate_project(project)
        workspace = test_service_collection.workspace_service.create_workspace(
            project=project,
            initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
            source_branch=None,
            requested_branch_name=None,
            description="Test workspace",
            transaction=transaction,
        )
        workspace_id = workspace.object_id

    # target_branch was auto-resolved
    assert workspace.target_branch == "origin/main"

    # Request diff with target branch included
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        diff = test_service_collection.workspace_service.get_workspace_diff(
            workspace_id, transaction, force_refresh=True, include_target_branch_diff=True
        )

    assert diff is not None
    assert diff.target_branch_diff != ""
    assert "new_file.txt" in diff.target_branch_diff


def test_diff_skipped_when_no_target_branch(
    test_service_collection: CompleteServiceCollection,
    test_root_concurrency_group: ConcurrencyGroup,
    tmp_path: Path,
) -> None:
    """Target branch diff should be empty when workspace has no target_branch.

    Constructs a repo with no remotes and a non-default branch name so that
    neither the remote-tracking nor local main/master fallback resolves.
    """
    repo_path = _create_isolated_git_repo(tmp_path / "no_remote_repo", test_root_concurrency_group)

    # Rename main to a non-default name so the local main/master fallback
    # finds nothing.
    subprocess.run(
        ["git", "-C", str(repo_path), "branch", "-m", "main", "develop"],
        check=True,
        capture_output=True,
    )

    # Add a file so there's something to diff
    (repo_path / "new_file.txt").write_text("content")
    subprocess.run(["git", "-C", str(repo_path), "add", "new_file.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repo_path), "commit", "-m", "Add file"],
        check=True,
        capture_output=True,
    )

    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        project = test_service_collection.project_service.initialize_project(
            project_path=repo_path,
            organization_reference=ANONYMOUS_ORGANIZATION_REFERENCE,
            transaction=transaction,
        )
        test_service_collection.project_service.activate_project(project)
        workspace = test_service_collection.workspace_service.create_workspace(
            project=project,
            initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
            source_branch=None,
            requested_branch_name=None,
            description="No target branch",
            transaction=transaction,
        )
        workspace_id = workspace.object_id

    assert workspace.target_branch is None

    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        diff = test_service_collection.workspace_service.get_workspace_diff(
            workspace_id, transaction, force_refresh=True, include_target_branch_diff=True
        )

    assert diff is not None
    # With no target_branch, target_branch_diff should be empty (not a failed lookup)
    assert diff.target_branch_diff == ""


def _create_in_place_workspace(test_service_collection: CompleteServiceCollection, repo_path: Path) -> WorkspaceID:
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        project = test_service_collection.project_service.initialize_project(
            project_path=repo_path,
            organization_reference=ANONYMOUS_ORGANIZATION_REFERENCE,
            transaction=transaction,
        )
        test_service_collection.project_service.activate_project(project)
        workspace = test_service_collection.workspace_service.create_workspace(
            project=project,
            initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
            source_branch=None,
            requested_branch_name=None,
            description="Isolated repo workspace",
            transaction=transaction,
        )
    return workspace.object_id


def test_workspace_diff_includes_untracked_files_whose_names_start_with_a_dash(
    test_service_collection: CompleteServiceCollection,
    test_root_concurrency_group: ConcurrencyGroup,
    tmp_path: Path,
) -> None:
    repo_path = _create_isolated_git_repo(tmp_path / "repo", test_root_concurrency_group)
    workspace_id = _create_in_place_workspace(test_service_collection, repo_path)
    (repo_path / "-dash.txt").write_text("dash content\n")

    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        diff = test_service_collection.workspace_service.get_workspace_diff(
            workspace_id, transaction, force_refresh=True, include_target_branch_diff=True
        )

    assert diff is not None
    assert "+++ b/-dash.txt" in diff.uncommitted_diff
    assert "+++ b/-dash.txt" in diff.target_branch_diff


def _read_head_commit(repo_path: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()


def _commit_all(repo_path: Path, message: str) -> str:
    subprocess.run(["git", "-C", str(repo_path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo_path), "commit", "-m", message], check=True, capture_output=True)
    return _read_head_commit(repo_path)


def test_commit_history_reports_a_file_type_change_as_modified(
    test_service_collection: CompleteServiceCollection,
    test_root_concurrency_group: ConcurrencyGroup,
    tmp_path: Path,
) -> None:
    repo_path = _create_isolated_git_repo(tmp_path / "repo", test_root_concurrency_group)
    subprocess.run(["git", "-C", str(repo_path), "checkout", "-b", "feature"], check=True, capture_output=True)
    workspace_id = _create_in_place_workspace(test_service_collection, repo_path)
    (repo_path / "README.md").unlink()
    (repo_path / "README.md").symlink_to("elsewhere.md")
    commit_hash = _commit_all(repo_path, "Turn the readme into a symlink")

    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        commits, fork_point = test_service_collection.workspace_service.get_commit_history(workspace_id, transaction)

    assert [commit.hash for commit in commits] == [commit_hash]
    assert [(change.path, change.status) for change in commits[0].files] == [("README.md", "M")]
    assert fork_point is not None


def test_get_commit_diff_resolves_an_abbreviated_hash_and_its_parent(
    test_service_collection: CompleteServiceCollection,
    test_root_concurrency_group: ConcurrencyGroup,
    tmp_path: Path,
) -> None:
    repo_path = _create_isolated_git_repo(tmp_path / "repo", test_root_concurrency_group)
    workspace_id = _create_in_place_workspace(test_service_collection, repo_path)
    parent_hash = _read_head_commit(repo_path)
    (repo_path / "added.txt").write_text("added\n")
    commit_hash = _commit_all(repo_path, "Add a file")

    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        diff_text, resolved_hash, resolved_parent = test_service_collection.workspace_service.get_commit_diff(
            workspace_id, commit_hash[:10], transaction
        )
        with pytest.raises(ValueError):
            test_service_collection.workspace_service.get_commit_diff(workspace_id, "not-a-hash", transaction)

    assert "+++ b/added.txt" in diff_text
    assert resolved_hash == commit_hash
    assert resolved_parent == parent_hash


def test_read_file_at_ref_reads_a_ref_starting_with_a_dash_as_a_revision_not_an_option(
    test_service_collection: CompleteServiceCollection,
    test_root_concurrency_group: ConcurrencyGroup,
    tmp_path: Path,
) -> None:
    repo_path = _create_isolated_git_repo(tmp_path / "repo", test_root_concurrency_group)
    workspace_id = _create_in_place_workspace(test_service_collection, repo_path)

    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        content_at_head = test_service_collection.workspace_service.read_file_at_ref(
            workspace_id, "README.md", "HEAD", transaction
        )
        with pytest.raises(FileNotFoundAtRefError):
            test_service_collection.workspace_service.read_file_at_ref(
                workspace_id, "README.md", "--format=format:injected", transaction
            )

    assert content_at_head == FileAtRefResult(content="test", encoding="utf-8")


def test_discard_file_restores_tracked_files_deletes_untracked_ones_and_rejects_paths_outside_the_checkout(
    test_service_collection: CompleteServiceCollection,
    test_root_concurrency_group: ConcurrencyGroup,
    tmp_path: Path,
) -> None:
    repo_path = _create_isolated_git_repo(tmp_path / "repo", test_root_concurrency_group)
    workspace_id = _create_in_place_workspace(test_service_collection, repo_path)
    (repo_path / "README.md").write_text("edited")
    (repo_path / "untracked.txt").write_text("untracked")
    workspace_service = test_service_collection.workspace_service

    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        tracked_result = workspace_service.discard_file(workspace_id, "README.md", transaction)
        untracked_result = workspace_service.discard_file(workspace_id, "untracked.txt", transaction)
        traversal_result = workspace_service.discard_file(workspace_id, "../outside.txt", transaction)

    assert tracked_result.success
    assert (repo_path / "README.md").read_text() == "test"
    assert untracked_result.success
    assert not (repo_path / "untracked.txt").exists()
    assert not traversal_result.success
    assert traversal_result.error_message == "Path traversal is not allowed"


def test_get_workspace_files_lists_tracked_and_untracked_files_but_not_ignored_ones(
    test_service_collection: CompleteServiceCollection,
    test_root_concurrency_group: ConcurrencyGroup,
    tmp_path: Path,
) -> None:
    repo_path = _create_isolated_git_repo(tmp_path / "repo", test_root_concurrency_group)
    workspace_id = _create_in_place_workspace(test_service_collection, repo_path)
    (repo_path / ".gitignore").write_text("ignored.txt\n")
    (repo_path / "ignored.txt").write_text("ignored")
    (repo_path / "nested").mkdir()
    (repo_path / "nested" / "untracked.txt").write_text("untracked")

    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        file_paths = test_service_collection.workspace_service.get_workspace_files(workspace_id, transaction)

    assert file_paths == [".gitignore", "README.md", "nested/untracked.txt"]


def test_get_workspace_files_raises_files_unavailable_when_the_checkout_is_not_a_repository(
    test_service_collection: CompleteServiceCollection,
    test_project: Project,
    tmp_path: Path,
) -> None:
    environment_dir = tmp_path / f"environment-{uuid4().hex}"
    (environment_dir / "code").mkdir(parents=True)
    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        workspace = test_service_collection.workspace_service.create_workspace(
            project=test_project,
            initialization_strategy=WorkspaceInitializationStrategy.CLONE,
            source_branch=None,
            requested_branch_name=None,
            description="Checkout without a repository",
            transaction=transaction,
        )
        transaction.update_workspace_fields(workspace.object_id, environment_id=str(environment_dir))

    with test_service_collection.data_model_service.open_transaction(request_id=RequestID()) as transaction:
        with pytest.raises(WorkspaceFilesUnavailableError):
            test_service_collection.workspace_service.get_workspace_files(workspace.object_id, transaction)


def test_get_cached_current_branch_does_not_create_the_branch_poller(
    test_service_collection: CompleteServiceCollection,
    test_root_concurrency_group: ConcurrencyGroup,
) -> None:
    """The accessor is a pure cache read: on a service whose poller has never
    been built it must return None WITHOUT constructing the polling machinery."""
    fresh_service = DefaultWorkspaceService.build(
        concurrency_group=test_root_concurrency_group,
        settings=test_service_collection.settings,
        data_model_service=test_service_collection.data_model_service,
        project_service=test_service_collection.project_service,
        dependency_management_service=test_service_collection.dependency_management_service,
    )

    assert fresh_service.get_cached_current_branch(WorkspaceID()) is None
    assert fresh_service._branch_poller_instance is None


def test_get_cached_current_branch_returns_none_for_unknown_workspace(
    test_service_collection: CompleteServiceCollection,
) -> None:
    assert test_service_collection.workspace_service.get_cached_current_branch(WorkspaceID()) is None
