import threading
import time
from queue import Empty
from queue import Queue
from typing import Callable
from typing import Final
from typing import TypeVar

from loguru import logger
from watchdog.events import EVENT_TYPE_CLOSED
from watchdog.events import FileModifiedEvent

from sculptor.interfaces.environments.v1.base import Environment
from sculptor.interfaces.environments.v1.constants import ENVIRONMENT_WORKSPACE_DIRECTORY
from sculptor.primitives.threads import ObservableThread
from sculptor.services.local_sync_service._debounce_and_watchdog_helpers import SlightlySaferObserver
from sculptor.services.local_sync_service.path_batch_scheduler import FileSystemEvent

T = TypeVar("T")
_KEEPALIVE_SECONDS = 10
_POLL_SECONDS = 1

# watchmedo already ignores {EVENT_TYPE_OPENED, EVENT_TYPE_CLOSED_NO_WRITE}
# https://github.com/gorakhargosh/watchdog/blob/4bc8f79bee96ee26a854ae940d8d17265e705673/src/watchdog/tricks/__init__.py#L102
_EXTRA_EVENT_TYPE_TO_IGNORE: Final = EVENT_TYPE_CLOSED
_WATCHMEDO_BASH_COMMAND: Final = " && ".join(
    (
        f'[[ ${{watch_event_type}} != "{_EXTRA_EVENT_TYPE_TO_IGNORE}" ]]',
        "echo ${watch_src_path}",
        "echo ${watch_dest_path}",
    )
)

_WATCHMEDO_FOR_NULL_DELIMITED_AGENT_PATHS_VIA_ENVIRONMENT: Final = (
    "/imbue/nix_bin/watchmedo",
    "shell-command",
    # "--patterns=*", defaults to **
    # WOULD BE GREAT TO USE THIS FEATURE EXCEPT OH WAIT THE LAST RELEASED VERSION OF WATCHDOG WAS FROM 2024
    # f"--ignore-patterns=";".join((".git/objects/**", ".git/index", ".git/*.lock", ".git/logs/**"))
    "--recursive",
    #  We filter for watch_event_type == "closed" because each file change triggers many
    #  duplicate events, but only one "closed" event.
    f'--command=bash -c "{_WATCHMEDO_BASH_COMMAND}"',
    str(ENVIRONMENT_WORKSPACE_DIRECTORY),
)


class HackedFileSystemEvent(FileModifiedEvent):
    pass


# TODO: Dedupe with helper in streams.py
def _empty_update_queue(
    updates_queue: Queue[T], shutdown_event: threading.Event, is_blocking_allowed: bool
) -> list[T]:
    """Empties the queue and returns all items in it."""
    all_data: list[T] = []

    # first get everything that's already in the queue
    while updates_queue.qsize() > 0:
        data = updates_queue.get()
        all_data.append(data)

    # if there was anything at all, we can return it immediately
    if len(all_data) > 0:
        return all_data

    # if we can't block, we're done
    if not is_blocking_allowed:
        return all_data

    # otherwise, if we're allowed to block, we can wait for more data
    start_time = time.monotonic()
    while True:
        try:
            data = updates_queue.get(timeout=_POLL_SECONDS)
        except Empty:
            if shutdown_event.is_set():
                logger.info("Server is stopping, no more updates will be sent.")
                return []
            if time.monotonic() - start_time > _KEEPALIVE_SECONDS:
                return all_data
            else:
                continue
        else:
            # might as well go return the rest of it too
            all_data = [data] + _empty_update_queue(updates_queue, shutdown_event, is_blocking_allowed=False)
            return all_data

    assert False, "This should never be reached, as we either return or raise an exception in the loop above."


def pipe_synthetic_events_from_environment_file_watcher_into_queue(
    environment: Environment, stopped_event: threading.Event, sink: Callable[[FileSystemEvent], None]
) -> None:
    cmd = _WATCHMEDO_FOR_NULL_DELIMITED_AGENT_PATHS_VIA_ENVIRONMENT
    watchmedo_process = environment.run_process_in_background(cmd, {}, shutdown_event=stopped_event, run_as_root=True)

    for single_path_line, is_stdout in watchmedo_process.stream_stdout_and_stderr():
        single_path_line = single_path_line.strip()
        if not is_stdout:
            # logger.error("WATCHMEDO ERR: " + single_path_line)
            continue
        if single_path_line != "":
            # logger.trace(f"WATCHMEDO: {single_path_line}")
            sink(HackedFileSystemEvent(src_path=single_path_line))
    logger.trace("Watchmedo process has exited.")


def hack_watchmedo_watcher_into_watchdog_event_queue(
    observer: SlightlySaferObserver, agent_environment: Environment
) -> ObservableThread:
    # we don't really care about watchdog's internal semantics
    arbitrarily_extracted_emitter = next(iter(observer.emitters))
    sink = arbitrarily_extracted_emitter.queue_event
    return ObservableThread(
        target=pipe_synthetic_events_from_environment_file_watcher_into_queue,
        args=(agent_environment, observer.stopped_event, sink),
    )
