import json
import threading
import time
from contextlib import closing
from contextlib import contextmanager
from queue import Queue
from typing import Any
from typing import Generator

import httpx
import pytest
import requests
import uvicorn
from fastapi import Depends
from fastapi import FastAPI
from loguru import logger
from uvicorn import Config
from websocket import create_connection
from websockets.sync.connection import Connection

from imbue_core.agents.data_types.ids import AgentMessageID
from imbue_core.async_monkey_patches import log_exception
from imbue_core.common import generate_id
from imbue_core.constants import ExceptionPriority
from imbue_core.ids import AssistantMessageID
from imbue_core.itertools import only
from imbue_core.sculptor.state.chat_state import TextBlock
from imbue_core.sculptor.state.messages import ResponseBlockAgentMessage
from imbue_core.thread_utils import ObservableThread
from sculptor.config.settings import SculptorSettings
from sculptor.database.models import Notification
from sculptor.database.models import NotificationID
from sculptor.database.models import Project
from sculptor.primitives.ids import RequestID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.web.app import APP
from sculptor.web.app_basic_test import create_saved_agent_message_and_task
from sculptor.web.auth import authenticate_anonymous
from sculptor.web.derived import TaskUpdate
from sculptor.web.middleware import get_settings
from sculptor.web.middleware import services_factory

IS_WEBSOCKET = True


class ServerWithReadyFlag(uvicorn.Server):
    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._ready_event = threading.Event()

    async def main_loop(self) -> None:
        self._ready_event.set()
        await super().main_loop()


class AlreadyStartedServiceCollection(CompleteServiceCollection):
    """
    The service collection is already started in the fixture.

    When we run the app, in its lifespan, it's trying to start the collection again.

    This class fakes the start method to do nothing.

    """

    def start_all(self) -> None:
        pass


@pytest.fixture
def server_app(
    test_settings: SculptorSettings, test_services: CompleteServiceCollection
) -> Generator[FastAPI, None, None]:
    def override_get_settings() -> SculptorSettings:
        return test_settings

    def override_services_factory(settings: SculptorSettings = Depends(get_settings)) -> CompleteServiceCollection:
        return AlreadyStartedServiceCollection(
            settings=test_services.settings,
            data_model_service=test_services.data_model_service,
            environment_service=test_services.environment_service,
            secrets_service=test_services.secrets_service,
            anthropic_credentials_service=test_services.anthropic_credentials_service,
            git_repo_service=test_services.git_repo_service,
            task_service=test_services.task_service,
            project_service=test_services.project_service,
            local_sync_service=test_services.local_sync_service,
            configuration_broadcast_service=test_services.configuration_broadcast_service,
        )

    APP.dependency_overrides[get_settings] = override_get_settings
    APP.dependency_overrides[services_factory] = override_services_factory
    yield APP
    APP.dependency_overrides.clear()


@pytest.fixture
def server_url(server_app: FastAPI) -> Generator[str, None, None]:
    # Start server in a separate thread
    config = uvicorn.Config(app=server_app, host="127.0.0.1", port=0, log_level="debug")
    server = ServerWithReadyFlag(config)
    server_thread = ObservableThread(target=server.run)
    server_thread.start()

    # Wait for server to be actually ready
    server._ready_event.wait()

    # figure out what port was bound
    server_port = only(only(server.servers).sockets).getsockname()[-1]

    # Now make requests using the actual port
    yield f"http://127.0.0.1:{server_port}"

    server_app.shutdown_event.set()
    server.should_exit = True
    server_thread.join()


def test_server_runs(server_url: str) -> None:
    response = requests.get(server_url + "/api/")
    assert response.content


@contextmanager
def stream_response(url: str) -> Generator[Queue, None, None]:
    queue = Queue()
    is_done = threading.Event()
    if IS_WEBSOCKET:
        url = url + "/ws"
        with closing(create_connection(url.replace("http://", "ws://"))) as ws:
            thread = ObservableThread(
                target=_stream_lines_into_queue_from_websocket,
                args=(ws, is_done, queue),
                suppressed_exceptions=(Exception,),
            )
            thread.start()

            try:
                yield queue
            finally:
                is_done.set()
                # note that you cannot do this:
                # thread.join()
                # because the reader is synchronous and will block which takes a long time.
                # Instead, we simply have that thread understand that it has been stopped.
    else:
        with httpx.Client() as client:
            with client.stream("GET", url, timeout=httpx.Timeout(30.0, read=15.0)) as response:
                thread = ObservableThread(
                    target=_stream_lines_into_queue,
                    args=(response, is_done, queue),
                    suppressed_exceptions=(Exception,),
                )
                thread.start()

                try:
                    yield queue
                finally:
                    is_done.set()
                    response.close()
                    client.close()
                    # note that you cannot do this:
                    # thread.join()
                    # because the reader is synchronous and will block which takes a long time.
                    # Instead, we simply have that thread understand that it has been stopped.


def _stream_lines_into_queue(response, is_done: threading.Event, queue: Queue) -> None:
    try:
        # Check if the request was successful
        if response.status_code == 200:
            # Iterate over the response line by line
            for line in response.iter_lines():
                if is_done.is_set():
                    break
                if line:
                    if line.startswith("data: "):
                        queue.put(line[6:])
    except Exception as e:
        if is_done.is_set():
            # If the stream was closed, we don't care about the exception
            logger.trace("Ignoring exception in streaming response because the stream is closed: {}", e)
            return
        else:
            log_exception(e, "Unexpected error while streaming response", priority=ExceptionPriority.MEDIUM_PRIORITY)
            raise


def _stream_lines_into_queue_from_websocket(ws: Connection, is_done: threading.Event, queue: Queue) -> None:
    try:
        # Iterate over the response line by line
        while True:
            if is_done.is_set():
                break
            line = ws.recv()
            assert isinstance(line, str)
            if line.strip() != "null":
                queue.put(line)
    except Exception as e:
        if is_done.is_set():
            # If the stream was closed, we don't care about the exception
            logger.trace("Ignoring exception in streaming response because the stream is closed: {}", e)
            return
        else:
            log_exception(e, "Unexpected error while streaming response", priority=ExceptionPriority.MEDIUM_PRIORITY)
            raise


def test_task_stream(server_url: str, test_services: CompleteServiceCollection, test_project: Project) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        task = create_saved_agent_message_and_task(transaction, user_session, test_project, test_services)

    url = server_url + f"/api/v1/projects/{test_project.object_id}/tasks/{task.object_id}/stream"
    with stream_response(url) as queue:
        # get the initial state
        result = queue.get(timeout=10)
        state = TaskUpdate.model_validate_json(result)
        assert state.task_id == task.object_id
        # this is NOT racey, because this test runs with the task service spawn thread suppressed (is_spawner_suppressed)
        # thus, it does not actually start running the task.

        with user_session.open_transaction(test_services) as transaction:
            message_id = AgentMessageID()
            test_services.task_service.create_message(
                ResponseBlockAgentMessage(
                    message_id=message_id,
                    role="assistant",
                    assistant_message_id=AssistantMessageID(generate_id()),
                    content=(TextBlock(text="this is a unique test message"),),
                ),
                task.object_id,
                transaction,
            )

        # check that we get notified of the update
        result = queue.get(timeout=10)
        updated_state = TaskUpdate.model_validate_json(result)
        assert updated_state.in_progress_chat_message is not None
        assert any(
            [
                content_block
                for content_block in updated_state.in_progress_chat_message.content
                if isinstance(content_block, TextBlock) and content_block.text == "this is a unique test message"
            ]
        )


def test_tasks_stream(server_url: str, test_services: CompleteServiceCollection, test_project: Project) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())

    url = server_url + f"/api/v1/projects/{test_project.object_id}/tasks/stream"
    with stream_response(url) as queue:
        # get the initial state
        result = queue.get(timeout=10)
        state = json.loads(result)
        assert len(state["taskByTaskId"]) == 0

        # add a task
        with user_session.open_transaction(test_services) as transaction:
            _task = create_saved_agent_message_and_task(transaction, user_session, test_project, test_services)

        # check that we get notified of the update
        result = queue.get(timeout=10)
        updated_state = json.loads(result)
        assert only(updated_state["taskByTaskId"].values())["id"] == str(_task.object_id)


def _get_first_notifications_message(queue: Queue[Any], seen: list[dict], allowed_unrelated_messages: int = 3) -> dict:
    while len(seen) <= allowed_unrelated_messages:
        result = queue.get(timeout=5)
        state_update = json.loads(result)
        seen.append(state_update)
        if state_update["notifications"]:
            break
        assert len(seen) <= 3, f"no notifications seen in and {allowed_unrelated_messages=} exceeded. {seen=}"
    return state_update


def test_user_notification_stream(
    server_url: str,
    test_services: CompleteServiceCollection,
    test_project: Project,
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())

    url = server_url + f"/api/v1/projects/{test_project.object_id}/notifications/stream"
    with stream_response(url) as queue:
        # get the initial state
        result = queue.get(timeout=10)
        initial_state = json.loads(result)
        # first result should include project
        assert only(initial_state["projects"])["objectId"] == str(test_project.object_id)

        # add a user notification
        with user_session.open_transaction(test_services) as transaction:
            notification = Notification(
                object_id=NotificationID(), message="Test notification", user_reference=user_session.user_reference
            )
            transaction.insert_notification(notification)

        state_update = _get_first_notifications_message(queue, [initial_state])
        notifications = state_update["notifications"]
        assert len(notifications) == 1, f"Expected 1 notification, got {len(notifications)}: {notifications}"
        assert only(notifications)["message"] == notification.message, (
            f"Expected message '{notification.message}', got '{only(notifications)['message']}': {notifications}"
        )


def test_multiple_streams(server_url: str, test_services: CompleteServiceCollection, test_project: Project) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    user_update_request_id = str(user_session.request_id)

    tasks_stream_url = f"{server_url}/api/v1/projects/{test_project.object_id}/tasks/stream"
    notifications_url = f"{server_url}/api/v1/projects/{test_project.object_id}/notifications/stream"

    with (
        stream_response(tasks_stream_url) as task_queue,
        stream_response(notifications_url) as notification_queue,
    ):
        # get the initial state
        task_queue.get(timeout=10)

        # add a user notification
        with user_session.open_transaction(test_services) as transaction:
            notification = Notification(
                object_id=NotificationID(), message="Test notification", user_reference=user_session.user_reference
            )
            transaction.insert_notification(notification)

        # check that we get notified of the update on both sides
        user_update = _get_first_notifications_message(notification_queue, [])
        notifications = user_update["notifications"]
        assert len(notifications) == 1, f"Expected 1 notification, got {len(notifications)}: {notifications}"
        assert only(notifications)["message"] == notification.message, (
            f"Expected message '{notification.message}', got '{only(notifications)['message']}': {notifications}"
        )
        assert user_update_request_id in user_update["finishedRequestIds"], (
            f"Expected request ID '{user_update_request_id}' to be in finished request IDs. {user_update=}"
        )

        start_time = time.monotonic()
        while time.monotonic() - start_time < 5:
            task_update = json.loads(task_queue.get(timeout=10))
            if user_update_request_id in task_update["finishedRequestIds"]:
                return
        raise TimeoutError(
            f"Did not receive the expected request ID in the task update stream within 5 seconds. {task_update=}, {user_update=}"
        )
