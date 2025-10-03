import json
import os
import time
from pathlib import Path
from queue import Queue
from threading import Event
from typing import Any
from typing import Callable

from loguru import logger

from imbue_core.async_monkey_patches import log_exception

_JSONLRecord = dict[str, Any]


def observe_jsonl_log_file(
    jsonl_log_file_path: Path,
    output_queue: Queue[_JSONLRecord],
    filter_fn: Callable[[_JSONLRecord], bool],
    stop_event: Event,
    check_interval: float = 0.1,
) -> None:
    """
    Observe a JSONL file, by putting each new JSON object that passes the filter function into the output queue.

    Set stop_event to stop the observation.

    Assumes that the file is *append-only* (hence the "log" in the name).
    Assumes that the file is encoded in UTF-8.
    """

    # note that this implementation is slightly more complex than you might expect.
    # this is due to the fact that there are no non-blocking file read operations in Python.
    # to work around this, we exploit the fact that this is an append-only file.
    # we can thus simply ask the OS how large the file is, and never try to read too many new bytes.

    # the other bit of complexity comes from the fact, because we are reading based on bytes, we could get incomplete lines.
    # this is handled by buffering the raw bytes and only decoding them when we have a complete line.

    # this while loop at the top is just to retry if the file goes missing -- only really happens rarely, during a test, etc
    # but the most reasonable thing to do is to simply retry from the beginning
    # the user may delete it as well.
    while True:
        try:
            # wait for the log to get created
            while not jsonl_log_file_path.exists():
                if stop_event.is_set():
                    return
                time.sleep(0.1)

            # Open the file in binary mode to read raw bytes so that we can handle incomplete lines
            with open(jsonl_log_file_path, "rb") as f:
                last_position = 0

                # Buffer for incomplete lines
                raw_buffer = b""

                while not stop_event.is_set():
                    # Get current file size
                    current_size = os.path.getsize(jsonl_log_file_path)

                    # Check if file has grown
                    if current_size > last_position:
                        # Calculate how much to read
                        bytes_to_read = current_size - last_position

                        # Read exactly the new bytes
                        chunk = f.read(bytes_to_read)

                        if chunk:
                            # Update position
                            last_position = f.tell()

                            # Add to buffer
                            raw_buffer += chunk

                            # Process complete lines
                            try:
                                str_buffer = raw_buffer.decode("utf-8", errors="replace")
                            except UnicodeDecodeError:
                                # TODO: this means that any log that is not valid utf-8 will stop being streamed
                                # if it's not valid, just wait...
                                continue

                            # otherwise let's see if we've got any complete lines
                            lines = str_buffer.split("\n")

                            # All but the last element are complete lines
                            for line in lines[:-1]:
                                try:
                                    json_data = json.loads(line)
                                except json.JSONDecodeError:
                                    logger.error("Failed to parse JSON: {}", line)
                                    continue
                                else:
                                    if filter_fn(json_data):
                                        output_queue.put(json_data)

                            # Keep the incomplete line in buffer
                            raw_buffer = lines[-1].encode("utf-8")
                    elif current_size < last_position:
                        raise Exception("File size decreased, possible truncation or rotation detected.")
                        # # File was truncated/rotated
                        # # Reset to beginning or end depending on your needs
                        # f.seek(0)
                        # last_position = f.tell()
                        # raw_buffer = ""  # Clear buffer since file was reset
                    else:
                        # No new data, wait before checking again
                        stop_event.wait(check_interval)

                # can't do this, not json decodable
                # # Put any remaining buffered content
                # if raw_buffer:
                #     line_queue.put(raw_buffer.decode("utf-8", errors="replace"))

                return

        except FileNotFoundError:
            continue
        except BaseException as e:
            log_exception(e, "Failure in file watcher thread")
            raise
