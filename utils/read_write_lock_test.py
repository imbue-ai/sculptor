import threading
import time
from concurrent.futures import ThreadPoolExecutor

from sculptor.utils.read_write_lock import ReadWriteLock


def _reader_task(lock: ReadWriteLock, barrier: threading.Barrier) -> None:
    """Ensure all readers can enter together."""
    with lock.read_lock():
        barrier.wait(timeout=1.0)


def test_readers_run_concurrently() -> None:
    lock = ReadWriteLock()
    num_readers = 3
    barrier = threading.Barrier(num_readers)

    with ThreadPoolExecutor(max_workers=num_readers) as executor:
        futures = [executor.submit(_reader_task, lock, barrier) for _ in range(num_readers)]
        for future in futures:
            future.result()


def _writer_with_signals(
    lock: ReadWriteLock,
    events: list[str],
    release_event: threading.Event,
    acquired_event: threading.Event,
) -> None:
    with lock.write_lock():
        acquired_event.set()
        events.append("writer_start")
        release_event.wait()
        events.append("writer_end")


def _reader_with_record(
    lock: ReadWriteLock,
    events: list[str],
    reader_id: int,
    started_event: threading.Event,
) -> None:
    started_event.set()
    with lock.read_lock():
        events.append(f"reader_{reader_id}")
        time.sleep(0.001)


def test_writer_blocks_readers() -> None:
    lock = ReadWriteLock()
    events: list[str] = []
    release_writer = threading.Event()
    writer_acquired = threading.Event()

    writer_thread = threading.Thread(
        target=_writer_with_signals,
        args=(lock, events, release_writer, writer_acquired),
    )
    writer_thread.start()
    writer_acquired.wait()

    reader_started = threading.Event()
    reader_thread = threading.Thread(
        target=_reader_with_record,
        args=(lock, events, 1, reader_started),
    )
    reader_thread.start()
    reader_started.wait()

    assert events == ["writer_start"]

    release_writer.set()
    writer_thread.join()
    reader_thread.join()

    assert events == ["writer_start", "writer_end", "reader_1"]


def _writer_task(lock: ReadWriteLock, events: list[str], hold_event: threading.Event | None = None) -> None:
    with lock.write_lock():
        events.append("writer_start")
        if hold_event:
            hold_event.wait()
        else:
            time.sleep(0.01)
        events.append("writer_end")


def test_multiple_writers_serialize() -> None:
    lock = ReadWriteLock()
    events: list[str] = []

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(_writer_task, lock, events) for _ in range(3)]
        for future in futures:
            future.result()

    expected = ["writer_start", "writer_end"] * 3
    assert events == expected


def test_readers_wait_for_writer_then_proceed() -> None:
    lock = ReadWriteLock()
    events: list[str] = []
    release_writer = threading.Event()
    writer_acquired = threading.Event()

    writer_thread = threading.Thread(
        target=_writer_with_signals,
        args=(lock, events, release_writer, writer_acquired),
    )
    writer_thread.start()
    writer_acquired.wait()

    reader_threads: list[threading.Thread] = []
    reader_started_events: list[threading.Event] = []
    for i in range(3):
        started = threading.Event()
        thread = threading.Thread(
            target=_reader_with_record,
            args=(lock, events, i, started),
        )
        thread.start()
        reader_threads.append(thread)
        reader_started_events.append(started)

    for started in reader_started_events:
        started.wait()

    assert events == ["writer_start"]

    release_writer.set()
    writer_thread.join()
    for thread in reader_threads:
        thread.join()

    assert events[0] == "writer_start"
    assert events[1] == "writer_end"
    assert set(events[2:]) == {"reader_0", "reader_1", "reader_2"}
    assert len(events) == 5


def _blocking_reader(
    lock: ReadWriteLock,
    entered_event: threading.Event,
    release_event: threading.Event,
) -> None:
    with lock.read_lock():
        entered_event.set()
        release_event.wait()


def _waiting_writer(lock: ReadWriteLock, started_event: threading.Event, entered_event: threading.Event) -> None:
    started_event.set()
    with lock.write_lock():
        entered_event.set()


def test_writer_waits_until_reader_releases() -> None:
    lock = ReadWriteLock()
    reader_entered = threading.Event()
    reader_release = threading.Event()
    writer_entered = threading.Event()

    reader_thread = threading.Thread(
        target=_blocking_reader,
        args=(lock, reader_entered, reader_release),
    )
    reader_thread.start()
    reader_entered.wait()

    writer_started = threading.Event()
    writer_thread = threading.Thread(
        target=_waiting_writer,
        args=(lock, writer_started, writer_entered),
    )
    writer_thread.start()
    writer_started.wait()
    assert not writer_entered.is_set()

    reader_release.set()
    reader_thread.join()
    writer_thread.join()
    assert writer_entered.is_set()


def _blocking_writer(
    lock: ReadWriteLock,
    started_event: threading.Event,
    entered_event: threading.Event,
    release_event: threading.Event,
) -> None:
    started_event.set()
    with lock.write_lock():
        entered_event.set()
        release_event.wait()


def _waiting_reader(
    lock: ReadWriteLock,
    started_event: threading.Event,
    entered_event: threading.Event,
) -> None:
    started_event.set()
    with lock.read_lock():
        entered_event.set()


def test_new_readers_block_while_writer_waits() -> None:
    lock = ReadWriteLock()
    first_reader_entered = threading.Event()
    release_first_reader = threading.Event()
    writer_entered = threading.Event()
    writer_released = threading.Event()
    late_reader_started = threading.Event()
    late_reader_entered = threading.Event()

    first_reader_thread = threading.Thread(
        target=_blocking_reader,
        args=(lock, first_reader_entered, release_first_reader),
    )
    first_reader_thread.start()
    first_reader_entered.wait()

    writer_started = threading.Event()
    writer_thread = threading.Thread(
        target=_blocking_writer,
        args=(lock, writer_started, writer_entered, writer_released),
    )
    writer_thread.start()
    writer_started.wait()
    assert not writer_entered.is_set()

    late_reader_thread = threading.Thread(
        target=_waiting_reader,
        args=(lock, late_reader_started, late_reader_entered),
    )
    late_reader_thread.start()
    late_reader_started.wait()
    assert not late_reader_entered.is_set()

    release_first_reader.set()
    writer_entered.wait(timeout=1.0)
    assert writer_entered.is_set()

    writer_released.set()
    late_reader_thread.join(timeout=1.0)
    assert late_reader_entered.is_set()
    writer_thread.join()
    first_reader_thread.join()
