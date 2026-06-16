import json
import threading
import time
from contextlib import closing
from contextlib import contextmanager
from queue import Queue
from typing import Any
from typing import Callable
from typing import Generator

import pytest
import requests
import uvicorn
from fastapi import Depends
from fastapi import FastAPI
from loguru import logger
from uvicorn import Config
from websocket import create_connection
from websockets.sync.connection import Connection

from sculptor.config.settings import SculptorSettings
from sculptor.database.models import Notification
from sculptor.database.models import NotificationID
from sculptor.database.models import Project
from sculptor.foundation.async_monkey_patches import log_exception
from sculptor.foundation.common import generate_id
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.constants import ExceptionPriority
from sculptor.foundation.itertools import only
from sculptor.foundation.thread_utils import ObservableThread
from sculptor.primitives.ids import AgentMessageID
from sculptor.primitives.ids import AssistantMessageID
from sculptor.primitives.ids import RequestID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.state.chat_state import TextBlock
from sculptor.state.messages import ResponseBlockAgentMessage
from sculptor.web.app import APP
from sculptor.web.app_basic_test import _create_task_with_message_in_workspace
from sculptor.web.app_basic_test import _create_workspace
from sculptor.web.auth import authenticate_anonymous
from sculptor.web.middleware import get_settings
from sculptor.web.middleware import services_factory


class ServerWithReadyFlag(uvicorn.Server):
    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self._ready_event = threading.Event()

    async def main_loop(self) -> None:
        self._ready_event.set()
        await super().main_loop()


@pytest.fixture
def server_app(
    test_settings: SculptorSettings, test_already_started_services: CompleteServiceCollection
) -> Generator[FastAPI, None, None]:
    def override_get_settings() -> SculptorSettings:
        return test_settings

    def override_services_factory(
        concurrency_group: ConcurrencyGroup, settings: SculptorSettings = Depends(get_settings)
    ) -> CompleteServiceCollection:
        return test_already_started_services

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
    # pyre-ignore[16]: pyre doesn't understand the way server is initialized and it's a third-party library so we can't fix it
    server_port = only(only(server.servers).sockets).getsockname()[-1]

    # Now make requests using the actual port
    yield f"http://127.0.0.1:{server_port}"

    server_app.shutdown_event.set()  # pyre-fixme[16]: the source of shutdown_event is unknown
    server.should_exit = True
    server_thread.join()


def test_server_runs(server_url: str) -> None:
    response = requests.get(server_url + "/api/")
    assert response.content


@contextmanager
def stream_response(url: str) -> Generator[Queue[str], None, None]:
    queue = Queue()
    is_done = threading.Event()
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


def _stream_lines_into_queue_from_websocket(ws: Connection, is_done: threading.Event, queue: Queue[str]) -> None:
    try:
        # Iterate over the response line by line
        while True:
            if is_done.is_set():
                break
            line = ws.recv()
            assert isinstance(line, str)
            if line.strip() not in ("null", ""):
                queue.put(line)
    except Exception as e:
        if is_done.is_set():
            # If the stream was closed, we don't care about the exception
            logger.trace("Ignoring exception in streaming response because the stream is closed: {}", e)
            return
        else:
            log_exception(e, "Unexpected error while streaming response", priority=ExceptionPriority.MEDIUM_PRIORITY)
            raise


def _next_streaming_update(queue: Queue[str], timeout: float = 15.0) -> dict[str, Any]:
    raw = queue.get(timeout=timeout)
    return json.loads(raw)


def _poll_for_update(
    queue: Queue[str], predicate: Callable[[dict[str, Any]], bool], total_timeout: float = 25.0
) -> dict[str, Any]:
    start_time = time.time()
    last_update = None

    while time.time() - start_time < total_timeout:
        remaining_time = total_timeout - (time.time() - start_time)
        update = _next_streaming_update(queue, timeout=remaining_time)
        last_update = update
        if predicate(update):
            return update

    raise AssertionError(
        f"Did not receive expected update within {total_timeout}s. Last update received: {last_update}"
    )


def _get_task_update(update: dict[str, Any], task_id) -> dict[str, Any] | None:
    key = str(task_id)
    task_updates = update.get("taskUpdateByTaskId", {})
    return task_updates.get(key, None)


def test_unified_stream_emits_task_updates(
    server_url: str, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = _create_workspace(transaction, test_services, test_project)
        task = _create_task_with_message_in_workspace(
            transaction, user_session, test_project, test_services, workspace
        )

    stream_url = server_url + "/api/v1/stream/ws"
    with stream_response(stream_url) as queue:
        initial_update = _next_streaming_update(queue)
        task_update = _get_task_update(initial_update, task.object_id)
        assert task_update is not None, f"Task {task.object_id} not found in initial update"
        assert isinstance(task_update, dict)
        assert task_update.get("chatMessages") is not None

        with user_session.open_transaction(test_services) as transaction:
            message_id = AgentMessageID()
            test_services.task_service.create_message(
                ResponseBlockAgentMessage(
                    message_id=message_id,
                    role="assistant",
                    assistant_message_id=AssistantMessageID(generate_id()),
                    content=(TextBlock(text="streaming smoke test message"),),
                ),
                task.object_id,
                transaction,
            )

        # Keep reading updates until we get the task update with the new message
        updated = _poll_for_update(queue, predicate=lambda u: _get_task_update(u, task.object_id) is not None)
        task_update = _get_task_update(updated, task.object_id)
        assert task_update is not None, "Did not receive task update after creating message"
        in_progress = task_update.get("inProgressChatMessage")
        assert in_progress is not None
        # Check that the message text is in the content blocks
        content_blocks = in_progress.get("content", [])
        assert any(
            block.get("text") == "streaming smoke test message"
            for block in content_blocks
            if block.get("type") == "text"
        )


def test_unified_stream_emits_notifications_and_finished_requests(
    server_url: str, test_services: CompleteServiceCollection, test_project: Project
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())

    stream_url = server_url + "/api/v1/stream/ws"
    with stream_response(stream_url) as queue:
        _next_streaming_update(queue)

        # Create a notification to trigger a transaction with a request ID
        with user_session.open_transaction(test_services) as transaction:
            notification = Notification(
                object_id=NotificationID(),
                message="Test notification from unified stream",
                user_reference=user_session.user_reference,
            )
            transaction.insert_notification(notification)

        def _has_notification(update: dict[str, Any]) -> bool:
            user_update = update.get("userUpdate", {})
            notifications = user_update.get("notifications", [])
            return any(entry.get("message") == notification.message for entry in notifications)

        update = _poll_for_update(queue, predicate=_has_notification)
        finished_request_ids = update.get("finishedRequestIds", [])
        user_update = update.get("userUpdate", {})
        notifications = user_update.get("notifications", [])

        assert any(entry.get("message") == notification.message for entry in notifications)

        # Just verify that we got some finished request IDs in the stream
        assert len(finished_request_ids) > 0, "Should receive finished request IDs in the stream"
