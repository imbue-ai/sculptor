"""Unit tests for :mod:`sculptor.primitives.threads`."""

import time
from queue import Queue

from imbue_core.concurrency_group import ConcurrencyGroup
from sculptor.primitives.threads import StopGapBackgroundPollingStreamSource
from sculptor.primitives.threads import StopPolling


def _wait_until_thread_done(source: StopGapBackgroundPollingStreamSource, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while source.thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.02)


def test_source_polls_and_emits_values(test_root_concurrency_group: ConcurrencyGroup) -> None:
    """Baseline: a normal callback keeps emitting distinct values onto the queue."""
    queue: Queue[int] = Queue()
    values = iter([1, 2, 2, 3])

    def callback() -> int | None:
        try:
            return next(values)
        except StopIteration:
            return None

    source: StopGapBackgroundPollingStreamSource[int] = StopGapBackgroundPollingStreamSource(
        polling_callback=callback,
        output_queue=queue,
        check_interval_in_seconds=0.01,
        concurrency_group=test_root_concurrency_group,
    )
    source.start()
    time.sleep(0.2)
    source.stop()

    drained = []
    while not queue.empty():
        drained.append(queue.get())
    # Duplicate consecutive values are de-duplicated by the source.
    assert drained == [1, 2, 3]


def test_source_stops_itself_when_callback_raises_stop_polling(
    test_root_concurrency_group: ConcurrencyGroup,
) -> None:
    """A callback that raises ``StopPolling`` must terminate its source's thread
    *gracefully* — the source sets its stop event and the thread exits without
    recording an exception. This is the mechanism that lets a poller give up on
    a torn-down workspace repo instead of retrying forever (SCU-1429)."""
    queue: Queue[int] = Queue()
    call_count = {"n": 0}

    def callback() -> int | None:
        call_count["n"] += 1
        raise StopPolling("resource is gone")

    source: StopGapBackgroundPollingStreamSource[int] = StopGapBackgroundPollingStreamSource(
        polling_callback=callback,
        output_queue=queue,
        check_interval_in_seconds=0.01,
        concurrency_group=test_root_concurrency_group,
    )
    source.start()
    _wait_until_thread_done(source)

    assert not source.thread.is_alive(), "source thread should stop itself after StopPolling"
    assert source.stop_event.is_set(), "source should mark itself stopped after StopPolling"
    assert source.thread.exception_raw is None, "StopPolling should be handled gracefully, not crash the thread"
    # The callback should not keep being invoked after it asked to stop.
    invocations_at_stop = call_count["n"]
    time.sleep(0.1)
    assert call_count["n"] == invocations_at_stop, "callback must not be invoked again after StopPolling"

    # stop() remains a safe no-op once the thread has already exited.
    source.stop()
