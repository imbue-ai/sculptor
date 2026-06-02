import os
from pathlib import Path
from queue import Empty
from typing import cast

import pytest

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.git import get_repo_base_path
from sculptor.config.settings import SculptorSettings
from sculptor.database.models import Project
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.primitives.constants import ANONYMOUS_ORGANIZATION_REFERENCE
from sculptor.primitives.ids import RequestID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.data_model_service.api import TaskDataModelService
from sculptor.services.workspace_service.environment_manager.api import EnvironmentManager
from sculptor.services.workspace_service.environment_manager.default_implementation import DefaultEnvironmentManager
from sculptor.services.workspace_service.environment_manager.environments.local_environment import LocalEnvironment


@pytest.fixture
def test_project(test_settings: SculptorSettings, test_service_collection: CompleteServiceCollection) -> Project:
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
    assert project is not None, "By now, the project should be initialized."
    return project


@pytest.fixture
def environment_manager(
    test_settings: SculptorSettings,
    test_service_collection: CompleteServiceCollection,
) -> EnvironmentManager:
    """Create an EnvironmentManager for testing.

    Note: EnvironmentManager is an internal implementation detail of WorkspaceService.
    These tests exist to verify the low-level environment functionality.
    """
    return DefaultEnvironmentManager(
        data_model_service=cast(TaskDataModelService, test_service_collection.data_model_service),
    )


def test_simple_local_environment_run(
    initial_commit_repo: tuple[Path, str],
    environment_manager: EnvironmentManager,
    tmp_path: Path,
    test_project: Project,
    test_root_concurrency_group: ConcurrencyGroup,
) -> None:
    """Test creating a local environment and running a process in it."""
    project_path = initial_commit_repo[0]

    # Create environment directly with project path (no image concept)
    environment = environment_manager.create_environment(
        project_path=project_path,
        project_id=test_project.object_id,
        concurrency_group=test_root_concurrency_group,
    )
    try:
        process = environment.run_process_in_background(["echo", "hello"], secrets={})
        queue = process.get_queue()
        while not process.is_finished() or not queue.empty():
            try:
                line, is_stdout = queue.get(timeout=0.1)
            except Empty:
                continue
            if is_stdout:
                assert line.strip() == "hello"
    finally:
        environment.close()


def test_simple_local_environment_run_with_content(
    initial_commit_repo: tuple[Path, str],
    environment_manager: EnvironmentManager,
    tmp_path: Path,
    test_project: Project,
    test_root_concurrency_group: ConcurrencyGroup,
) -> None:
    """Test that files in the project path are accessible in the environment."""
    project_path = initial_commit_repo[0]

    # Create a test file in the project directory
    test_file_name = "test_file.txt"
    test_file_content = "hello"
    (project_path / test_file_name).write_text(test_file_content)

    # Create environment directly with project path
    environment = environment_manager.create_environment(
        project_path=project_path,
        project_id=test_project.object_id,
        concurrency_group=test_root_concurrency_group,
    )
    try:
        # The environment should be able to access files in the project directory
        process = environment.run_process_in_background(["cat", test_file_name], secrets={})
        queue = process.get_queue()
        while not process.is_finished() or not queue.empty():
            try:
                line, is_stdout = queue.get(timeout=0.1)
            except Empty:
                continue
            if is_stdout:
                assert line.strip() == test_file_content
    finally:
        environment.close()


def test_create_environment_directly(
    initial_commit_repo: tuple[Path, str],
    test_root_concurrency_group: ConcurrencyGroup,
    environment_manager: EnvironmentManager,
    test_project: Project,
) -> None:
    """Test creating an environment directly from a project path."""
    project_path = initial_commit_repo[0]

    # Create environment directly
    environment = environment_manager.create_environment(
        project_path=project_path,
        project_id=test_project.object_id,
        concurrency_group=test_root_concurrency_group,
    )

    try:
        # Verify the environment is working
        assert environment.is_alive()
        # Verify the workspace points to the project path
        assert isinstance(environment, LocalEnvironment)
    finally:
        environment.close()


def test_resume_environment(
    initial_commit_repo: tuple[Path, str],
    test_root_concurrency_group: ConcurrencyGroup,
    environment_manager: EnvironmentManager,
    test_project: Project,
) -> None:
    """Test resuming an environment from an environment ID."""
    project_path = initial_commit_repo[0]

    # Create initial environment
    environment = environment_manager.create_environment(
        project_path=project_path,
        project_id=test_project.object_id,
        concurrency_group=test_root_concurrency_group,
    )
    environment_id = environment.environment_id
    environment.close()

    # Resume the environment using the explicit resume_environment method
    resumed_environment = environment_manager.resume_environment(
        environment_id=environment_id,
        project_path=project_path,
        project_id=test_project.object_id,
        concurrency_group=test_root_concurrency_group,
    )

    try:
        # Verify the environment is working
        assert resumed_environment.is_alive()
        assert resumed_environment.environment_id == environment_id
    finally:
        resumed_environment.destroy()


def _create_clone_with_env_file(
    project_path: Path,
    env_content: str,
    environment_manager: EnvironmentManager,
    test_project: Project,
    concurrency_group: ConcurrencyGroup,
) -> str:
    """Create a clone environment with a .sculptor/.env file and return its environment_id."""
    env_dir = project_path / ".sculptor"
    env_dir.mkdir(parents=True, exist_ok=True)
    (env_dir / ".env").write_text(env_content)

    environment = environment_manager.create_environment(
        project_path=project_path,
        project_id=test_project.object_id,
        concurrency_group=concurrency_group,
        initialization_strategy=WorkspaceInitializationStrategy.CLONE,
    )
    environment_id = environment.environment_id
    environment.close()
    return environment_id


def test_resume_environment_recopies_env_file_in_clone_mode(
    initial_commit_repo: tuple[Path, str],
    test_root_concurrency_group: ConcurrencyGroup,
    environment_manager: EnvironmentManager,
    test_project: Project,
) -> None:
    """Resume in clone mode should re-copy .sculptor/.env from the source repo."""
    project_path = initial_commit_repo[0]
    environment_id = _create_clone_with_env_file(
        project_path, "RESUME_VAR=original\n", environment_manager, test_project, test_root_concurrency_group
    )

    (project_path / ".sculptor" / ".env").write_text("RESUME_VAR=updated\n")

    resumed = environment_manager.resume_environment(
        environment_id=environment_id,
        project_path=project_path,
        project_id=test_project.object_id,
        concurrency_group=test_root_concurrency_group,
        initialization_strategy=WorkspaceInitializationStrategy.CLONE,
        sculptor_folder=project_path / "fake_sculptor",
    )

    try:
        assert isinstance(resumed, LocalEnvironment)
        assert resumed._project_env_vars == {"RESUME_VAR": "updated"}
    finally:
        resumed.destroy()


def test_resume_environment_deletes_env_file_when_source_removed(
    initial_commit_repo: tuple[Path, str],
    test_root_concurrency_group: ConcurrencyGroup,
    environment_manager: EnvironmentManager,
    test_project: Project,
) -> None:
    """Resume in clone mode should delete dest .env if source .env no longer exists."""
    project_path = initial_commit_repo[0]
    environment_id = _create_clone_with_env_file(
        project_path, "TEMP_VAR=will_be_removed\n", environment_manager, test_project, test_root_concurrency_group
    )

    (project_path / ".sculptor" / ".env").unlink()

    resumed = environment_manager.resume_environment(
        environment_id=environment_id,
        project_path=project_path,
        project_id=test_project.object_id,
        concurrency_group=test_root_concurrency_group,
        initialization_strategy=WorkspaceInitializationStrategy.CLONE,
        sculptor_folder=project_path / "fake_sculptor",
    )

    try:
        assert isinstance(resumed, LocalEnvironment)
        assert resumed._project_env_vars == {}
        dest_env = resumed.get_working_directory() / ".sculptor" / ".env"
        assert not dest_env.exists()
    finally:
        resumed.destroy()
