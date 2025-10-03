import os
import tempfile
from pathlib import Path
from queue import Empty

import pytest

from imbue_core.git import get_repo_base_path
from sculptor.config.settings import SculptorSettings
from sculptor.database.models import Project
from sculptor.interfaces.environments.v1.base import LocalImageConfig
from sculptor.primitives.constants import ANONYMOUS_ORGANIZATION_REFERENCE
from sculptor.primitives.ids import RequestID
from sculptor.services.anthropic_credentials_service.api import AnthropicCredentialsService
from sculptor.services.data_model_service.api import DataModelService
from sculptor.services.environment_service.default_implementation import DefaultEnvironmentService
from sculptor.services.git_repo_service.api import GitRepoService
from sculptor.services.git_repo_service.data_types import GitRepoServiceCollection
from sculptor.services.project_service.api import ProjectService
from sculptor.services.secrets_service.api import SecretsService


@pytest.fixture
def test_service_collection(
    test_settings: SculptorSettings,
    test_secrets_service: SecretsService,
    test_anthropic_credentials_service: AnthropicCredentialsService,
    test_data_model_service: DataModelService,
    test_git_repo_service: GitRepoService,
    test_project_service: ProjectService,
) -> GitRepoServiceCollection:
    environment_service = DefaultEnvironmentService(
        settings=test_settings,
        git_repo_service=test_git_repo_service,
        data_model_service=test_data_model_service,
    )
    environment_service.start()
    return GitRepoServiceCollection(
        settings=test_settings,
        secrets_service=test_secrets_service,
        anthropic_credentials_service=test_anthropic_credentials_service,
        data_model_service=test_data_model_service,
        git_repo_service=test_git_repo_service,
        project_service=test_project_service,
        environment_service=environment_service,
    )


@pytest.fixture
def test_project(test_settings: SculptorSettings, test_service_collection: GitRepoServiceCollection) -> Project:
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


def test_fixtures(test_service_collection: GitRepoServiceCollection) -> None:
    pass


def test_simple_local_environment_run(
    initial_commit_repo: tuple[Path, str],
    test_service_collection: GitRepoServiceCollection,
    tmp_path: Path,
    test_project: Project,
) -> None:
    service = test_service_collection.environment_service
    config = LocalImageConfig(code_directory=tmp_path)
    with tempfile.TemporaryDirectory() as temp_dir:
        image = service.ensure_image(
            config,
            secrets={},
            active_repo_path=initial_commit_repo[0],
            cached_repo_path=Path(temp_dir),
            project_id=test_project.object_id,
        )
        with service.generate_environment(image, test_project.object_id) as environment:
            process = environment.run_process_in_background(["echo", "hello"], secrets={})
            queue = process.get_queue()
            while not process.is_finished() or not queue.empty():
                try:
                    line, is_stdout = queue.get(timeout=0.1)
                except Empty:
                    continue
                if is_stdout:
                    assert line.strip() == "hello"


def test_simple_local_environment_run_with_content(
    initial_commit_repo: tuple[Path, str],
    test_service_collection: GitRepoServiceCollection,
    tmp_path: Path,
    test_project: Project,
) -> None:
    service = test_service_collection.environment_service
    config = LocalImageConfig(code_directory=tmp_path)
    test_file_name = "test_file.txt"
    test_file_content = "hello"
    (tmp_path / test_file_name).write_text(test_file_content)
    with tempfile.TemporaryDirectory() as temp_dir:
        image = service.ensure_image(
            config,
            secrets={},
            active_repo_path=initial_commit_repo[0],
            cached_repo_path=Path(temp_dir),
            project_id=test_project.object_id,
        )
        with service.generate_environment(image, test_project.object_id) as environment:
            process = environment.run_process_in_background(["cat", test_file_name], secrets={})
            queue = process.get_queue()
            while not process.is_finished() or not queue.empty():
                try:
                    line, is_stdout = queue.get(timeout=0.1)
                except Empty:
                    continue
                if is_stdout:
                    assert line.strip() == test_file_content
