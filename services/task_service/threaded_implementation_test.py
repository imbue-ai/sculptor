import os
import queue
import time
from pathlib import Path

import pytest
from loguru import logger

from imbue_core.git import get_repo_base_path
from imbue_core.itertools import only
from imbue_core.sculptor.state.messages import Message
from sculptor.database.models import MustBeShutDownTaskInputsV1
from sculptor.database.models import Project
from sculptor.database.models import SendEmailTaskInputsV1
from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.interfaces.agents.v1.agent import TaskStatusRunnerMessage
from sculptor.primitives.ids import RequestID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.task_service.api import TaskMessageContainer
from sculptor.services.task_service.conftest import get_user_input_message
from sculptor.services.task_service.threaded_implementation import LocalThreadTaskService
from sculptor.services.task_service.threaded_implementation import ThreadRunner
from sculptor.services.task_service.threaded_implementation import _get_name_for_runner_from_task
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
        parent_task_id=None,
        input_data=SendEmailTaskInputsV1(subject="Hey there", message="How's it going?"),
    )


def get_run_forever_task(user_session: UserSession, project: Project) -> Task:
    return Task(
        object_id=TaskID(),
        user_reference=user_session.user_reference,
        organization_reference=user_session.organization_reference,
        project_id=project.object_id,
        parent_task_id=None,
        input_data=MustBeShutDownTaskInputsV1(),
    )


def assert_message_is_in_update(
    message_queue: queue.Queue[TaskMessageContainer], message: Message, task_id: TaskID, timeout: float = 10.0
) -> None:
    start_time = time.time()
    message_matched = False
    status_updated = False
    logger.trace("Searching for message: {}", message)
    while not (message_matched and status_updated) and time.time() - start_time < timeout:
        try:
            received_message_container = message_queue.get(timeout=1)
            logger.trace("Received message: {}", received_message_container)
            if any(received_message[0] == message for received_message in received_message_container.messages):
                message_matched = True
            if any(
                isinstance(received_message[0], TaskStatusRunnerMessage) and received_message[1] == task_id
                for received_message in received_message_container.messages
            ):
                status_updated = True
        except queue.Empty:
            continue

    assert message_matched and status_updated


def test_simple_task(test_service_collection: CompleteServiceCollection, specimen_project: Project) -> None:
    user_session = authenticate_anonymous(test_service_collection, RequestID())
    service = test_service_collection.task_service
    assert isinstance(service, LocalThreadTaskService)
    task = get_simple_task(user_session, specimen_project)
    with user_session.open_transaction(test_service_collection) as transaction:
        inserted_task = service.create_task(task, transaction)


def test_subscribe_to_user_messages(
    test_service_collection: CompleteServiceCollection, specimen_project: Project
) -> None:
    user_session = authenticate_anonymous(test_service_collection, RequestID())
    service = test_service_collection.task_service
    # add the task
    task = get_simple_task(user_session, specimen_project)
    with user_session.open_transaction(test_service_collection) as transaction:
        service.create_task(task, transaction)
    # add the first message
    first_user_message = get_user_input_message(task.object_id, "Hello, world!")
    with user_session.open_transaction(test_service_collection) as transaction:
        service.create_message(first_user_message, task.object_id, transaction)
    # subscribe to the messages
    with service.subscribe_to_user_and_sculptor_system_messages(task_id=task.object_id) as message_queue:
        # make sure that the queue already has the first message
        assert message_queue.get(timeout=1) == first_user_message
        # add a second message
        second_user_message = get_user_input_message(task.object_id, "Goodbye, world!")
        with user_session.open_transaction(test_service_collection) as transaction:
            service.create_message(second_user_message, task.object_id, transaction)
        # check that the queue receives the second message
        assert message_queue.get(timeout=1) == second_user_message


def test_subscribe_to_complete_tasks_for_user(
    test_service_collection: CompleteServiceCollection,
    specimen_project: Project,
) -> None:
    user_session = authenticate_anonymous(test_service_collection, RequestID())
    service = test_service_collection.task_service
    # add the task
    task = get_simple_task(user_session, specimen_project)
    with user_session.open_transaction(test_service_collection) as transaction:
        service.create_task(task, transaction)
    # add the first message
    first_user_message = get_user_input_message(task.object_id, "Hello, world!")
    with user_session.open_transaction(test_service_collection) as transaction:
        service.create_message(first_user_message, task.object_id, transaction)
    # subscribe to the messages
    with service.subscribe_to_complete_tasks_for_user(
        user_reference=task.user_reference, project_id=specimen_project.object_id
    ) as message_queue:
        # make sure that the queue already has the first message
        assert_message_is_in_update(message_queue, first_user_message, task.object_id)
        # add a second message
        second_user_message = get_user_input_message(task.object_id, "Goodbye, world!")
        with user_session.open_transaction(test_service_collection) as transaction:
            service.create_message(second_user_message, task.object_id, transaction)
        # check that the queue receives the second message
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

    assert len(service.runners) == 1
    runner: ThreadRunner = only(service.runners)
    assert _get_name_for_runner_from_task(task=task, task_id="") in runner.thread.name, (
        f"Runner name was: {runner.thread.name}"
    )
    assert runner.is_alive()

    service.stop()

    for runner in service.runners:
        assert not runner.is_alive(), f"Runner {runner.thread.name} is still alive!"
