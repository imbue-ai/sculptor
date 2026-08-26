"""Correlation registry matching renderer replies to `sculpt extension` requests.

A `sculpt extension` HTTP request publishes an ``ExtensionCommandUiAction`` over the
per-user WebSocket fan-out (see ``ui_actions``), then blocks on a per-correlation
queue here while every connected renderer POSTs its result back to
``/api/v1/extensions/command/{correlation_id}/result``. Each correlation id maps to a
``queue.Queue`` so the waiting request can drain however many replies arrive within
its window.

Module-level state mirrors ``ui_actions`` — both deliberately skip the Service /
service-collection plumbing because there is no lifecycle work to do. The HTTP
endpoints run in FastAPI's sync threadpool, so a plain thread-safe ``queue.Queue``
is the right primitive (no asyncio bridging needed).
"""

from queue import Queue
from threading import Lock

from sculptor.web.data_types import ExtensionCommandResult

_results_by_correlation_id: dict[str, "Queue[ExtensionCommandResult]"] = {}
_lock = Lock()


def open_correlation(correlation_id: str) -> "Queue[ExtensionCommandResult]":
    """Register a correlation id and return the queue its replies land in.

    The caller must ``close_correlation`` when done (typically in a ``finally``)
    so late replies for an abandoned request don't leak the queue.
    """
    result_queue: "Queue[ExtensionCommandResult]" = Queue()
    with _lock:
        _results_by_correlation_id[correlation_id] = result_queue
    return result_queue


def submit_result(correlation_id: str, result: ExtensionCommandResult) -> bool:
    """Deliver a renderer's reply. Returns False if nobody is waiting on it
    (already timed out / closed), so the result endpoint can stay quiet."""
    with _lock:
        result_queue = _results_by_correlation_id.get(correlation_id)
    if result_queue is None:
        return False
    result_queue.put(result)
    return True


def close_correlation(correlation_id: str) -> None:
    with _lock:
        _results_by_correlation_id.pop(correlation_id, None)
