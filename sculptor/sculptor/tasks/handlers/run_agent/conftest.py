from pathlib import Path
from typing import Generator
from typing import cast
from uuid import uuid4

import pytest

from sculptor.database.models import AgentTaskInputsV2
from sculptor.database.models import Project
from sculptor.database.models import Task
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.interfaces.agents.agent import HelloAgentConfig
from sculptor.primitives.ids import LocalEnvironmentID
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import TaskID
from sculptor.primitives.ids import UserReference
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.task_service.data_types import ServiceCollectionForTask
from sculptor.services.workspace_service.environment_manager.environments.local_environment import LOCAL_WORKSPACE_DIR
from sculptor.services.workspace_service.environment_manager.environments.local_environment import LocalEnvironment
from sculptor.state.messages import Message


@pytest.fixture
def project() -> Project:
    return Project(object_id=ProjectID(), name="Test Project", organization_reference=OrganizationReference("org_123"))


@pytest.fixture
def local_task(project: Project, tmp_path: Path) -> Task:
    return Task(
        object_id=TaskID(),
        organization_reference=project.organization_reference,
        user_reference=UserReference("usr_123"),
        project_id=project.object_id,
        input_data=AgentTaskInputsV2(
            agent_config=HelloAgentConfig(),
            git_hash="initialhash",
            system_prompt=None,
        ),
    )


@pytest.fixture
def services(
    test_service_collection: CompleteServiceCollection,
    test_root_concurrency_group: ConcurrencyGroup,
    local_task: Task,
    project: Project,
) -> Generator[ServiceCollectionForTask, None, None]:
    with test_service_collection.data_model_service.open_transaction(RequestID()) as transaction:
        transaction.upsert_project(project)
        test_service_collection.task_service.create_task(local_task, transaction)
    yield cast(ServiceCollectionForTask, test_service_collection)


@pytest.fixture
def environment(
    tmp_path: Path,
    project: Project,
    initial_commit_repo: tuple[Path, str],
    test_root_concurrency_group: ConcurrencyGroup,
) -> Generator[LocalEnvironment, None, None]:
    """Create a LocalEnvironment directly for testing.

    This fixture creates an environment without going through WorkspaceService,
    which is appropriate for unit tests that need direct environment access.
    """
    code_dir, _ = initial_commit_repo
    # Create workspace directory for state/artifacts
    workspace_dir = LOCAL_WORKSPACE_DIR / str(uuid4().hex)
    workspace_dir.mkdir(parents=True, exist_ok=True)

    environment = LocalEnvironment.create(
        environment_id=LocalEnvironmentID(str(workspace_dir)),
        project_id=project.object_id,
        concurrency_group=test_root_concurrency_group,
        repo_host_path=code_dir,
    )
    try:
        yield environment
    finally:
        environment.close()


def get_all_messages_for_task(task_id: TaskID, services: ServiceCollectionForTask) -> list[Message]:
    all_messages: list[Message] = []
    with services.task_service.subscribe_to_task(task_id) as queue:
        while queue.qsize() > 0:
            all_messages.append(queue.get_nowait())
    # remove the initial task state message
    all_messages.pop(0)
    return all_messages
