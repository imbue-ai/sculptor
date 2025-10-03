import abc
import math
import time
from typing import Generator
from typing import Mapping
from typing import Sequence

import modal
import modal.container_process
from loguru import logger

from sculptor.interfaces.environments.v1.base import ProviderTag
from sculptor.services.environment_service.providers.modal.errors import ModalProcessPidError

# The following two classes (SubprocessError and Proces) are legacy classes that we generally moved away from.
# The Modal environment hasn't been fully migrated yet so we still keep them around here for reference until it is.


class SubprocessError(Exception):
    def __init__(self, message: str, stderr: str | None = None, stdout: str | None = None) -> None:
        full_message = message
        if stdout:
            full_message += f"\nSTDOUT:\n{stdout}"
        if stderr:
            full_message += f"\nSTDERR:\n{stderr}"
        super().__init__(full_message)
        self.stderr = stderr
        self.stdout = stdout


class Process(abc.ABC):
    """Protocol defining interface for (remote and local) processes."""

    @abc.abstractmethod
    def get_extra_logger_context(self) -> Mapping[str, str | float | int | bool | None]: ...

    @abc.abstractmethod
    def read_stdout(self) -> str: ...

    @abc.abstractmethod
    def read_stderr(self) -> str: ...

    @abc.abstractmethod
    def stream_stdout(self) -> Generator[str, None, None]: ...

    @abc.abstractmethod
    def stream_stderr(self) -> Generator[str, None, None]: ...

    @property
    @abc.abstractmethod
    def returncode(self) -> int | None: ...

    @abc.abstractmethod
    def wait_and_read(self, timeout: float | None = None) -> tuple[str, str]:
        """Consumes stdout and stderr from the process and returns them as a tuple.

        This method uses subprocess.communicate() internally, which blocks until the process terminates
        and uses internal threads to consume stdout/stderr which will prevent blocking from when the
        buffers are full.

        This method cannot be used in conjunction with stream_stdout() or stream_stderr() since
        it will consume stdout/stderr from the process. If you need to stream stdout/stderr,
        you should use wait() instead.

        We will be making this interface less sus in a future ticket.
        """
        ...

    @abc.abstractmethod
    def wait(self, timeout: float | None = None) -> int:
        """Wait for the process to finish running and return the returncode.
        This method MUST be used in conjunction with stream_stdout() and stream_stderr() to prevent blocking when the buffers are full.

        We will be making this interface less sus in a future ticket.
        """
        ...

    @abc.abstractmethod
    def poll(self) -> int | None:
        """Poll process to check if the process has finished running.

        Returns None if the process is still running, otherwise returns the returncode.
        """
        ...

    @abc.abstractmethod
    def is_finished(self) -> bool:
        """Check if the process has finished running, returns True if it has finished, False otherwise."""
        ...

    @abc.abstractmethod
    def terminate(self, force_kill_seconds: float = 5.0) -> None:
        """
        Terminate the process gracefully, if it does not terminate within the specified time, force kill it.

        Raises:
            TimeoutProcessError: if the process could not be terminated gracefully or forcefully in time.
        """

    def check_output(self) -> str:
        self.wait()
        if self.returncode != 0:
            raise SubprocessError(
                f"Failed to run a process. Return code: {self.returncode}",
                stderr=self.read_stderr(),
                stdout=self.read_stdout(),
            )
        return self.read_stdout()


# TODO: more broadly, how do we deal with modal.exception.ConnectionError?
#  it is particularly tricky because we no longer no whether any of our commands worked or not...
#  and sure, we could retry continuously on it, but that *also* has problems...
class ModalProcess(Process):
    def __init__(
        self, process: modal.container_process.ContainerProcess[str], sandbox_id: str, command: Sequence[str], tag: str
    ) -> None:
        self.process = process
        self.sandbox_id = sandbox_id
        sandbox = modal.Sandbox.from_id(self.sandbox_id)

        # the following code is used to give us the pid so that we can terminate the process (which modal does not enable directly)
        get_pid_command = f"ps e -o pid,ppid,cmd $(pidof {command[0]})"
        get_pid_process = sandbox.exec(
            "bash",
            "-c",
            get_pid_command,
        )
        pid_output = get_pid_process.stdout.read().strip()
        all_parentless_tagged_lines = []
        for line in pid_output.split("\n"):
            parts = line.split()
            ppid = parts[1]
            cmd = " ".join(parts[2:])
            # when we use sandbox exec to start a process on modal, it apparently gets a ppid of 0
            # this is how we identify the process that we started (and distinguish it from its child processes that also have the tag)
            # if this is ever not the case, we will need to find a different way to identify the process that we started
            if f"SCULPTOR_PROCESS_TAG={tag}" in cmd and ppid == "0":
                all_parentless_tagged_lines.append(line)

        if len(all_parentless_tagged_lines) > 1:
            all_lines = "\n".join(all_parentless_tagged_lines)
            raise ModalProcessPidError(
                f"Expected no more than 1 PID, got {len(all_parentless_tagged_lines)} with tag {tag}: {all_lines}"
            )

        if len(all_parentless_tagged_lines) == 1:
            logger.info("PID: {}", all_parentless_tagged_lines[0])
            self.pid = int(all_parentless_tagged_lines[0].split()[0])

        self.stdout_buffer = []
        self.stderr_buffer = []

    def get_extra_logger_context(self) -> Mapping[str, str | float | int | bool | None]:
        return {"sandbox_id": self.sandbox_id, "provider": ProviderTag.MODAL}

    def read_stdout(self) -> str:
        self.stdout_buffer.append(self.process.stdout.read())
        return "".join(self.stdout_buffer)

    def read_stderr(self) -> str:
        self.stderr_buffer.append(self.process.stderr.read())
        return "".join(self.stderr_buffer)

    def stream_stdout(self) -> Generator[str, None, None]:
        buffer = ""
        for chunk in self.process.stdout:
            self.stdout_buffer.append(chunk)
            buffer += chunk
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                yield line + "\n"
        # Yield any remaining content in buffer (line without final newline)
        if buffer:
            yield buffer

    def stream_stderr(self) -> Generator[str, None, None]:
        buffer = ""
        for chunk in self.process.stderr:
            self.stderr_buffer.append(chunk)
            buffer += chunk
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                yield line + "\n"
        # Yield any remaining content in buffer (line without final newline)
        if buffer:
            yield buffer

    @property
    def returncode(self) -> int | None:
        return self.process.returncode

    def wait_and_read(self, timeout: float | None = None) -> tuple[str, str]:
        raise NotImplementedError("wait_and_read is not supported for modal processes")

    # pyre-fixme[7]: This function should always return an int, but could return None implicitly on timeout.
    def wait(self, timeout: float | None = None) -> int:
        # sadly, we have to busy wait here because modal's ContainerProcess.wait() does not support a timeout
        end_time = time.monotonic() + (timeout if timeout is not None else float("inf"))
        while time.monotonic() < end_time:
            exit_code = self.poll()
            if exit_code is None:
                time.sleep(0.1)
            else:
                return exit_code

    def poll(self) -> int | None:
        return self.process.poll()

    def is_finished(self) -> bool:
        return self.poll() is not None

    def terminate(self, force_kill_seconds: float = 5.0) -> None:
        if self.pid is None:
            return

        try:
            sandbox = modal.Sandbox.from_id(self.sandbox_id)
        except (modal.exception.SandboxTimeoutError, modal.exception.SandboxTerminatedError):
            # the process is definitely dead if we can't connect to the sandbox
            return

        process = sandbox.exec("kill", str(self.pid), timeout=math.ceil(force_kill_seconds))
        process.wait()
        if process.returncode != 0:
            process = sandbox.exec("kill", "-9", str(self.pid))
            process.wait()

        self.pid = None
