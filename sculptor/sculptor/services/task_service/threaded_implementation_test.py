import os
import queue
import time
from pathlib import Path
from typing import cast

import pytest
from loguru import logger

from sculptor.database.models import MustBeShutDownTaskInputsV1
from sculptor.database.models import NoOpTaskInputsV1
from sculptor.database.models import Project
from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.foundation.git import get_repo_base_path
from sculptor.foundation.itertools import only
from sculptor.interfaces.agents.agent import MessageTypes
from sculptor.interfaces.agents.tasks import TaskState
from sculptor.primitives.ids import RequestID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.task_service.api import TaskMessageContainer
from sculptor.services.task_service.conftest import get_user_input_message
from sculptor.services.task_service.threaded_implementation import LocalThreadTaskService
from sculptor.services.task_service.threaded_implementation import _get_name_for_runner_from_task
from sculptor.state.messages import Message
from sculptor.web.auth import UserSession
from sculptor.web.auth import authenticate_anonymous


@pytest.fixture
def specimen_project(test_service_collection: CompleteServiceCollection) -> Project:
    project_path: str | Path | None = os.getenv("PROJECT_PATH")
    if isinstance(project_path, str):
        project_path = Path(project_path)
    if not project_path:
        project_path = get_repo_base_path()
    user_session = authenticate_anonymous(test_service_collection, RequestID())
    with user_session.open_transaction(test_service_collection) as transaction:
        project = test_service_collection.project_service.initialize_project(
            project_path=project_path,
            organization_reference=user_session.organization_reference,
            transaction=transaction,
        )
    test_service_collection.project_service.activate_project(project)
    assert project is not None, "By now, the project should be initialized."
    return project


def get_simple_task(user_session: UserSession, project: Project) -> Task:
    return Task(
        object_id=TaskID(),
        user_reference=user_session.user_reference,
        organization_reference=user_session.organization_reference,
        project_id=project.object_id,
        input_data=NoOpTaskInputsV1(),
    )


def get_run_forever_task(user_session: UserSession, project: Project) -> Task:
    return Task(
        object_id=TaskID(),
        user_reference=user_session.user_reference,
        organization_reference=user_session.organization_reference,
        project_id=project.object_id,
        input_data=MustBeShutDownTaskInputsV1(),
    )


def assert_message_is_in_update(
    message_queue: queue.Queue[TaskMessageContainer], message: Message, task_id: TaskID, timeout: float = 30.0
) -> None:
    start_time = time.time()
    logger.trace("Searching for message: {}", message)
    while time.time() - start_time < timeout:
        try:
            received_message_container = message_queue.get(timeout=1)
            logger.trace("Received message: {}", received_message_container)
            if any(received_message[0] == message for received_message in received_message_container.messages):
                return
        except queue.Empty:
            continue

    assert False, f"Did not receive expected message within {timeout}s: {message}"


def test_simple_task(test_service_collection: CompleteServiceCollection, specimen_project: Project) -> None:
    user_session = authenticate_anonymous(test_service_collection, RequestID())
    service = test_service_collection.task_service
    assert isinstance(service, LocalThreadTaskService)
    task = get_simple_task(user_session, specimen_project)
    with user_session.open_transaction(test_service_collection) as transaction:
        service.create_task(task, transaction)


def test_delete_idle_task_finalizes_immediately(
    test_service_collection: CompleteServiceCollection, specimen_project: Project
) -> None:
    """Deleting a task that is not running should finalize it immediately (is_deleted=True),
    rather than leaving it stuck in is_deleting=True waiting for a runner that will never come."""
    user_session = authenticate_anonymous(test_service_collection, RequestID())
    service = test_service_collection.task_service
    assert isinstance(service, LocalThreadTaskService)

    # Create a task and wait for it to complete, so it has no active runner.
    task = get_simple_task(user_session, specimen_project)
    with user_session.open_transaction(test_service_collection) as transaction:
        service.create_task(task, transaction)

    # Wait for the task to finish running (the no-op task completes quickly).
    for _ in range(50):
        with user_session.open_transaction(test_service_collection) as transaction:
            current_task = service.get_task(task.object_id, transaction)
            if current_task is not None and current_task.outcome not in (TaskState.QUEUED, TaskState.RUNNING):
                break
        time.sleep(0.1)

    # Delete the completed (idle) task.
    with user_session.open_transaction(test_service_collection) as transaction:
        service.delete_task(task.object_id, transaction)

    # The task should be fully deleted, not stuck in is_deleting.
    with user_session.open_transaction(test_service_collection) as transaction:
        # get_task filters out deleted tasks, so use get_all_tasks to find it.
        # pyrefly: ignore [missing-attribute]
        all_tasks = transaction.get_all_tasks()
        deleted_task = next((t for t in all_tasks if t.object_id == task.object_id), None)
        assert deleted_task is not None, "Task should still exist in DB"
        assert deleted_task.is_deleted, "Idle task should be immediately finalized as deleted"
        assert not deleted_task.is_deleting, "is_deleting should be cleared after finalization"


def test_subscribe_to_user_messages(
    test_service_collection: CompleteServiceCollection, specimen_project: Project
) -> None:
    user_session = authenticate_anonymous(test_service_collection, RequestID())
    service = test_service_collection.task_service
    task = get_simple_task(user_session, specimen_project)
    with user_session.open_transaction(test_service_collection) as transaction:
        service.create_task(task, transaction)
    first_user_message = get_user_input_message(task.object_id, "Hello, world!")
    with user_session.open_transaction(test_service_collection) as transaction:
        service.create_message(cast(MessageTypes, first_user_message), task.object_id, transaction)
    with service.subscribe_to_user_and_sculptor_system_messages(task_id=task.object_id) as message_queue:
        # Ignore any sculptor system messages and wait for the first user message.
        for _ in range(99):
            message = message_queue.get(timeout=1)
            if message == first_user_message:
                break
        else:
            assert False, "Did not receive the first user message."
        second_user_message = get_user_input_message(task.object_id, "Goodbye, world!")
        with user_session.open_transaction(test_service_collection) as transaction:
            service.create_message(cast(MessageTypes, second_user_message), task.object_id, transaction)
        for _ in range(99):
            message = message_queue.get(timeout=1)
            if message == second_user_message:
                break
        else:
            assert False, "Did not receive the second user message."


def test_subscribe_to_complete_tasks_for_user(
    test_service_collection: CompleteServiceCollection,
    specimen_project: Project,
) -> None:
    user_session = authenticate_anonymous(test_service_collection, RequestID())
    service = test_service_collection.task_service
    task = get_simple_task(user_session, specimen_project)
    with user_session.open_transaction(test_service_collection) as transaction:
        service.create_task(task, transaction)
    first_user_message = get_user_input_message(task.object_id, "Hello, world!")
    with user_session.open_transaction(test_service_collection) as transaction:
        service.create_message(cast(MessageTypes, first_user_message), task.object_id, transaction)
    with service.subscribe_to_all_tasks_for_user(user_reference=task.user_reference) as message_queue:
        assert_message_is_in_update(message_queue, first_user_message, task.object_id)
        second_user_message = get_user_input_message(task.object_id, "Goodbye, world!")
        with user_session.open_transaction(test_service_collection) as transaction:
            service.create_message(cast(MessageTypes, second_user_message), task.object_id, transaction)
        assert_message_is_in_update(message_queue, second_user_message, task.object_id)


def test_task_service_proper_shutdown(
    test_service_collection: CompleteServiceCollection,
    specimen_project: Project,
) -> None:
    user_session = authenticate_anonymous(test_service_collection, RequestID())
    service = test_service_collection.task_service
    assert isinstance(service, LocalThreadTaskService)

    task = get_run_forever_task(user_session, specimen_project)
    with user_session.open_transaction(test_service_collection) as transaction:
        service.create_task(task, transaction)

    # wait a bit to ensure the task starts running
    time.sleep(2)

    assert len(service._runner_by_id) == 1
    runner = only(service._runner_by_id.values())
    fake_suffix = "tsk_01999999999999999999999999"
    gotten_name = _get_name_for_runner_from_task(task=task, task_id=TaskID(fake_suffix))
    assert gotten_name.endswith(fake_suffix)
    gotten_name_prefix = gotten_name[: -len(fake_suffix)]
    assert gotten_name_prefix in runner.get_name(), f"Runner name was {runner.get_name()}, but got {gotten_name}"
    assert runner.is_alive()

    service.stop()

    for runner in service._runner_by_id.values():
        assert not runner.is_alive(), f"Runner {runner.get_name()} is still alive!"
