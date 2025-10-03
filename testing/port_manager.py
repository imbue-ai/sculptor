import errno
import json
import random
import socket
import tempfile
from pathlib import Path

from filelock import FileLock


def _get_free_port(min_port: int = 24576, max_port: int = 32768) -> int:
    """Get a random free port from within the given range [min, max).

    Why 24576 to 32768? By default, s.bind(("", 0)) will return a port from the range [49152, 65536),
    which is the IANA-designated ephemeral port range.
    That means when tests are run locally, other processes may also be grabbing ports from within the same range.
    When I look at ports in use locally, I see some ports in use at lower ranges too, so I'm going lower still.

    Unfortunately there's also a mild TOCTTOU with the free-check: we must release the port between this check and
    giving it to the caller. In the meantime someone else could grab it.

    So moving to a less-used port range MAY decrease conflict frequency."""
    while True:
        port_to_try = random.randint(min_port, max_port)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", port_to_try))
                port = s.getsockname()[1]
                assert isinstance(port, int) and port == port_to_try
            except OSError as e:
                # port is already in use, try again
                assert e.errno == errno.EADDRINUSE, "should be EADDRINUSE or we have a real problem"
                continue
        return port


class PortManager:
    """A simple port manager for ensuring that no two tests try to use the same port.

    It works across multiple processes via a file lock.
    """

    def __init__(self) -> None:
        root_tmp_dir = tempfile.gettempdir()
        self.ports_used_file_path = Path(root_tmp_dir) / "ports_used.json"
        self.lock_file_path = Path(str(self.ports_used_file_path) + ".lock")

    def _get_ports_in_use(self, f) -> list[int]:
        content = f.read().strip()
        if content:
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                # If the file is corrupted, start fresh
                return []
        else:
            # Empty file, start fresh
            return []

    def get_free_port(self) -> int:
        with FileLock(self.lock_file_path):
            if self.ports_used_file_path.exists():
                with open(self.ports_used_file_path, "r") as f:
                    ports_in_use = self._get_ports_in_use(f)
            else:
                ports_in_use = []

            try:
                while True:
                    port = _get_free_port()
                    if port not in ports_in_use:
                        ports_in_use.append(port)
                        return port
            finally:
                with open(self.ports_used_file_path, "w") as f:
                    json.dump(ports_in_use, f)

    def release_port(self, port: int) -> None:
        with FileLock(self.lock_file_path):
            if not self.ports_used_file_path.exists():
                return
            with open(self.ports_used_file_path, "r") as f:
                ports_in_use = self._get_ports_in_use(f)

            try:
                ports_in_use.remove(port)
            except ValueError:
                pass
            with open(self.ports_used_file_path, "w") as f:
                json.dump(ports_in_use, f)

    def close(self) -> None:
        if self.ports_used_file_path.exists():
            self.ports_used_file_path.unlink()
        if self.lock_file_path.exists():
            self.lock_file_path.unlink()
