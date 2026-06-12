from queue import Queue
from typing import Generator

import pytest

from sculptor.primitives.ids import WorkspaceID
from sculptor.web.data_types import OpenFileUiAction
from sculptor.web.data_types import StreamingUpdateSourceTypes
from sculptor.web.ui_actions import _subscribers
from sculptor.web.ui_actions import add_subscriber
from sculptor.web.ui_actions import publish_ui_action
from sculptor.web.ui_actions import remove_subscriber


@pytest.fixture(autouse=True)
def _reset_registry() -> Generator[None, None, None]:
    _subscribers.clear()
    yield
    _subscribers.clear()


def test_publish_writes_to_registered_subscriber() -> None:
    queue: Queue[StreamingUpdateSourceTypes] = Queue()
    add_subscriber(queue.put_nowait)

    action = OpenFileUiAction(workspace_id=WorkspaceID(), file_path="/tmp/a.txt", mode="auto")
    publish_ui_action(action)

    assert queue.get_nowait() is action


def test_remove_subscriber_stops_delivery() -> None:
    queue: Queue[StreamingUpdateSourceTypes] = Queue()
    add_subscriber(queue.put_nowait)
    remove_subscriber(queue.put_nowait)

    publish_ui_action(OpenFileUiAction(workspace_id=WorkspaceID(), file_path="/tmp/a.txt", mode="auto"))

    assert queue.empty()


def test_publish_fans_out_to_all_subscribers() -> None:
    queue_a: Queue[StreamingUpdateSourceTypes] = Queue()
    queue_b: Queue[StreamingUpdateSourceTypes] = Queue()
    add_subscriber(queue_a.put_nowait)
    add_subscriber(queue_b.put_nowait)

    action = OpenFileUiAction(workspace_id=WorkspaceID(), file_path="/tmp/a.txt", mode="diff")
    publish_ui_action(action)

    assert queue_a.get_nowait() is action
    assert queue_b.get_nowait() is action


def test_publish_does_not_raise_when_subscriber_queue_full() -> None:
    full_queue: Queue[StreamingUpdateSourceTypes] = Queue(maxsize=1)
    full_queue.put_nowait(OpenFileUiAction(workspace_id=WorkspaceID(), file_path="/tmp/seed.txt", mode="auto"))
    add_subscriber(full_queue.put_nowait)

    publish_ui_action(OpenFileUiAction(workspace_id=WorkspaceID(), file_path="/tmp/a.txt", mode="auto"))
