"""Process-wide registry of subscribers for UI actions.

Endpoint code calls publish_ui_action(action); each registered subscriber
callback receives the action. Callbacks are added/removed by the
WebSocket entry point in stream_everything().

Module-level state mirrors local_terminal_manager — both deliberately
skip the Service / service-collection plumbing because there is no
lifecycle work to do.
"""

from queue import Full
from threading import Lock
from typing import Callable

from loguru import logger

from sculptor.primitives.ids import WorkspaceID
from sculptor.web.data_types import ExtensionCommandUiAction
from sculptor.web.data_types import OpenFileUiAction
from sculptor.web.data_types import WebviewCommandUiAction

UiAction = OpenFileUiAction | WebviewCommandUiAction | ExtensionCommandUiAction
UiActionSubscriber = Callable[[UiAction], object]

_subscribers: set[UiActionSubscriber] = set()
_lock = Lock()

_webview_seq_by_workspace_id: dict[WorkspaceID, int] = {}
_seq_lock = Lock()


def add_subscriber(subscriber: UiActionSubscriber) -> None:
    with _lock:
        _subscribers.add(subscriber)


def remove_subscriber(subscriber: UiActionSubscriber) -> None:
    with _lock:
        _subscribers.discard(subscriber)


def subscriber_count() -> int:
    """Number of connected stream subscribers (≈ one per renderer/WebSocket).

    The extension command endpoint uses this as an upper bound on how many
    renderer replies to expect, so a single-window setup returns as soon as
    that one renderer answers instead of always waiting out the timeout.
    """
    with _lock:
        return len(_subscribers)


def publish_ui_action(action: UiAction) -> None:
    with _lock:
        subscribers = list(_subscribers)
    for subscriber in subscribers:
        try:
            subscriber(action)
        except Full:
            logger.warning(
                "Dropping {} for workspace {}: subscriber queue full",
                type(action).__name__,
                action.workspace_id,
            )


def next_webview_seq(workspace_id: WorkspaceID) -> int:
    """Allocate a per-workspace monotonically increasing sequence number for
    webview commands. Lets the frontend distinguish a fresh command from a
    stale rerender even when consecutive commands are otherwise identical.
    """
    with _seq_lock:
        seq = _webview_seq_by_workspace_id.get(workspace_id, 0) + 1
        _webview_seq_by_workspace_id[workspace_id] = seq
    return seq
