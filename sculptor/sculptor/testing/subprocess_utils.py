import subprocess
import threading
from typing import Callable


class Forwarder(threading.Thread):
    """Thread to forward output from the sculptor server to the logger.

    While the sculptor server is running, there might be useful output that we want to log.
    """

    def __init__(
        self,
        sculptor_server: subprocess.Popen,
        prefix: str = "",
        known_harmless_func: Callable[[str], bool] | None = None,
    ) -> None:
        super().__init__(daemon=True)
        self.prefix = prefix
        self.sculptor_server = sculptor_server
        self.first_failure_line = None
        self.known_harmless_func = known_harmless_func
        self._stop_event = threading.Event()

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the thread to stop and wait for it to finish."""
        self._stop_event.set()
        self.join(timeout=timeout)

    def run(self) -> None:
        assert self.sculptor_server.stdout, "Sculptor server stdout is always available in PIPE mode"
        try:
            while not self._stop_event.is_set():
                line = self.sculptor_server.stdout.readline()
                if not line:
                    break
                # Note: the print(line) here routes to pytest junit due to an issue with how pytest hides stdout
                #       the logger actually displays to the user
                print_colored_line(self.prefix + line.rstrip(), known_harmless_func=self.known_harmless_func)
                if "|ERROR" in line or "Cache miss" in line:
                    # note that we do NOT blow up here -- that's because we want to capture all the output
                    self.first_failure_line = line.rstrip()
                    # raise RuntimeError(line.strip())
        except ValueError:
            # stdout was closed; exit gracefully
            pass


def print_colored_line(
    line: str, level: str | None = None, known_harmless_func: Callable[[str], bool] | None = None
) -> None:
    if known_harmless_func is not None and known_harmless_func(line):
        print(f"\033[32mKnown harmless: {line}\033[0m")
    elif "|ERROR" in line or level == "ERROR":
        # Red
        print(f"\033[31m{line}\033[0m")
    elif "|WARNING" in line or level == "WARNING":
        # Yellow
        print(f"\033[33m{line}\033[0m")
    elif "|INFO" in line or level == "INFO":
        # Green
        print(f"\033[32m{line}\033[0m")
    elif "|DEBUG" in line or level == "DEBUG":
        # Cyan
        print(f"\033[36m{line}\033[0m")
    elif "|TRACE" in line or level == "TRACE":
        # Gray
        # print(f"\033[90m{line}\033[0m")
        pass
    else:
        print(line)
