import os
import shlex
import subprocess
import time
from pathlib import Path
from queue import Queue
from threading import Event
from typing import Mapping
from typing import Sequence
from typing import TYPE_CHECKING
from typing import Union

from loguru import logger
from pydantic import AnyUrl
from pydantic import PrivateAttr
from tenacity import retry
from tenacity import stop_after_attempt
from tenacity import wait_exponential

from imbue_core.async_monkey_patches import log_exception
from imbue_core.common import generate_id
from imbue_core.constants import ExceptionPriority
from imbue_core.processes.local_process import RunningProcess
from imbue_core.processes.local_process import run_background
from imbue_core.processes.local_process import run_blocking
from imbue_core.retry_utils import log_before_sleep
from imbue_core.subprocess_utils import CompoundEvent
from imbue_core.subprocess_utils import ProcessError
from sculptor.interfaces.environments.v1.base import Environment
from sculptor.interfaces.environments.v1.base import LocalDockerEnvironmentConfig
from sculptor.interfaces.environments.v1.base import LocalDockerImage
from sculptor.interfaces.environments.v1.base import ProviderTag
from sculptor.interfaces.environments.v1.base import SSHD_SERVER_NAME
from sculptor.interfaces.environments.v1.constants import ENVIRONMENT_WORKSPACE_DIRECTORY
from sculptor.interfaces.environments.v1.constants import SCULPTOR_USER
from sculptor.interfaces.environments.v1.errors import EnvironmentFailure
from sculptor.interfaces.environments.v1.errors import FileNotFoundEnvironmentError
from sculptor.interfaces.environments.v1.errors import IsADirectoryEnvironmentError
from sculptor.interfaces.environments.v1.errors import ProviderError
from sculptor.interfaces.environments.v1.provider_status import OkStatus
from sculptor.primitives.ids import DockerContainerID
from sculptor.primitives.ids import DockerImageID
from sculptor.services.environment_service.environments.utils import check_provider_health_on_failure
from sculptor.services.environment_service.environments.utils import get_docker_status
from sculptor.services.environment_service.providers.docker.errors import ContainerNotRunningError
from sculptor.services.environment_service.providers.docker.errors import ContainerPausedError
from sculptor.services.environment_service.providers.docker.errors import ProviderIsDownError
from sculptor.tasks.handlers.run_agent.git import run_git_command_local
from sculptor.utils.read_write_lock import ReadWriteLock
from sculptor.utils.secret import Secret

if TYPE_CHECKING:
    from _typeshed import OpenBinaryModeReading
    from _typeshed import OpenTextModeReading


class DockerRunningProcess(RunningProcess):
    def __init__(
        self,
        command: Sequence[str],
        output_queue: Queue[tuple[str, bool]],
        shutdown_event: Event | CompoundEvent,
        tag: str,
        container_id: str,
        is_checked: bool = False,
    ) -> None:
        super().__init__(command, output_queue, shutdown_event, is_checked)
        self.tag = tag
        self.container_id = container_id
        self._inner_pid: int | None = None
        self._bad_first_line: str | None = None

    def wait_until_started(self) -> None:
        while self._inner_pid is None and self._bad_first_line is None:
            if self._completed_process is not None:
                return
            time.sleep(0.01)

        if self._inner_pid is not None:
            return

        line = self._bad_first_line
        # 'Error response from daemon: Container 6c68cfb608213a41c64810dda5c019dc57deece848f340546ec7eafffabe294c is paused, unpause the container before exec
        if line.startswith("Error response from daemon:") and line.rstrip().endswith(
            "is paused, unpause the container before exec"
        ):
            raise ContainerPausedError(f"Container {self.container_id} is not running (paused)")
        # Error response from daemon: container b705de75d78f697169502233f9b56f3c4162253e790cbbc71902ebec1aa8b7a3 is not running
        elif line.startswith("Error response from daemon:") and line.rstrip().endswith("is not running"):
            raise ContainerNotRunningError(f"Container {self.container_id} is not running")
        stdout = self.read_stdout()
        stderr = self.read_stderr()
        raise ProviderError(
            f"Unexpected first line from stderr - this usually indicates that something is wrong with docker {self._command}:\nstdout: {stdout}\nstderr: {line.strip()}\n{stderr}",
        )

    def on_line(self, line: str, is_stdout: bool) -> None:
        if not is_stdout and self._inner_pid is None:
            # Parse the PID from the format: "PID:SCULPTOR_PROCESS_TAG=tag"
            if f":SCULPTOR_PROCESS_TAG={self.tag}" in line:
                pid_str = line.strip().split(":")[0]
                self._inner_pid = int(pid_str)
                logger.trace("Discovered PID {} for process with tag {}", self._inner_pid, self.tag)
                return
            else:
                self._bad_first_line = line
                return
        super().on_line(line, is_stdout)

    def terminate(self, force_kill_seconds: float = 5.0) -> None:
        if self._inner_pid is not None:
            try:
                # Kill the process group (negative PID) to include all child processes
                # To use negative PID, we need to run as root
                run_blocking(
                    command=[
                        "docker",
                        "exec",
                        "--user",
                        "root",
                        self.container_id,
                        "bash",
                        "-c",
                        f"kill -TERM -{self._inner_pid} && if kill -0 -{self._inner_pid} 2>/dev/null; then tail --pid={self._inner_pid} -f /dev/null; fi",
                    ],
                    timeout=force_kill_seconds,
                )
            except ProcessError:
                # Force kill if SIGTERM didn't work
                try:
                    run_blocking(
                        command=[
                            "docker",
                            "exec",
                            "--user",
                            "root",
                            self.container_id,
                            "kill",
                            "-9",
                            f"-{self._inner_pid}",
                        ],
                        is_output_traced=False,
                    )
                except ProcessError as e:
                    if "no such process" in e.stderr.lower():
                        logger.debug("Process {} already gone", self._inner_pid)
                    else:
                        log_exception(e, "Failed to force kill process", priority=ExceptionPriority.LOW_PRIORITY)

        super().terminate(force_kill_seconds)


class DockerEnvironment(Environment):
    object_type: str = "DockerEnvironment"
    environment_id: DockerContainerID
    server_port_by_name: dict[str, int]
    config: LocalDockerEnvironmentConfig
    environment_prefix: str = ""
    _snapshot_guard: ReadWriteLock = PrivateAttr(default_factory=ReadWriteLock)

    @property
    def container_id(self) -> str:
        return self.environment_id

    def get_repo_url(self) -> AnyUrl:
        return AnyUrl(
            f"ssh://{SCULPTOR_USER}@localhost:{self.server_port_by_name[SSHD_SERVER_NAME]}{ENVIRONMENT_WORKSPACE_DIRECTORY}"
        )

    def get_snapshot_guard(self) -> ReadWriteLock:
        return self._snapshot_guard

    def push_into_environment_repo(self, user_repo_path: Path, src_branch_name: str, dst_branch_name: str) -> None:
        with self._snapshot_guard.read_lock():
            run_git_command_local(
                [
                    "git",
                    "push",
                    "--force",
                    "--no-verify",
                    str(self.get_repo_url()),
                    f"{src_branch_name}:{dst_branch_name}",
                ],
                cwd=user_repo_path,
                check_output=True,
                is_retry_safe=False,
            )

    def get_repo_url_for_mutagen(self) -> str:
        return (
            f"{SCULPTOR_USER}@localhost:{self.server_port_by_name[SSHD_SERVER_NAME]}:{ENVIRONMENT_WORKSPACE_DIRECTORY}"
        )

    def get_config(self) -> LocalDockerEnvironmentConfig:
        return self.config

    def get_file_mtime(self, path: str) -> float:
        with self._snapshot_guard.read_lock():
            try:
                result = run_blocking(
                    command=["docker", "exec", "--user", SCULPTOR_USER, self.container_id, "stat", "-c", "%Y", path],
                    is_output_traced=False,
                )
            except ProcessError as e:
                if "no such file or directory" in e.stderr.lower():
                    raise FileNotFoundEnvironmentError(f"Failed to get mtime for file {path}: {e.stderr}") from e
                else:
                    raise
        return float(result.stdout.strip())

    def get_extra_logger_context(self) -> Mapping[str, str | float | int | bool | None]:
        return {"container_id": self.container_id, "provider": ProviderTag.DOCKER}

    def _assemble_docker_exec_args(
        self,
        command: Sequence[str],
        cwd: str | None,
        secrets: Mapping[str, str | Secret],
        is_interactive: bool,
        run_as_root: bool,
        run_with_sudo_privileges: bool,
    ) -> tuple[list[str], str]:
        # TODO: Thad thinks run_with_sudo_privileges should just be a synonym for run_as_root, and we give the user the option to drop those privileges.
        # note -- we used to have -it here instead of -i, but it seems to be working fine with just -i
        #  and -t ends up causing issues with logging (the lines don't properly flush)
        docker_command = (
            ["docker", "exec"]
            # When running with sudo privileges, we need -u root in order to run setpriv later
            + (["-u", "root"] if run_with_sudo_privileges or run_as_root else ["-u", SCULPTOR_USER])
            + (["-i"] if is_interactive else [])
        )
        for key in secrets:
            docker_command.extend(["-e", f"{key}"])
        # Only set working directory if it exists or if no workspace path is needed
        if cwd:
            docker_command.extend(["-w", cwd])
        # FIXME: nope, this is sort of crazy, makes this slow by a factor of ~2.  Callers should simply ensure the dir exists if they want to use it.
        elif self.exists(str(self.get_workspace_path())):
            docker_command.extend(["-w", str(self.get_workspace_path())])
        tag = generate_id()
        # Wrap command to echo PID with tag to stderr first
        wrapped_command = (
            ["setpriv", f"--reuid={os.getuid()}", f"--regid={os.getgid()}", "--groups", "sculptoradmin"]
            if run_with_sudo_privileges
            else []
        ) + [
            "sh",
            "-c",
            f'echo "$$:SCULPTOR_PROCESS_TAG={tag}" >&2 && exec "$@"',
            "--",  # This is $0 for the shell
            *command,
        ]
        docker_command.extend([self.container_id, *wrapped_command])
        return docker_command, tag

    @check_provider_health_on_failure
    def run_process_in_background(
        self,
        command: Sequence[str],
        secrets: Mapping[str, str | Secret],
        cwd: str | None = None,
        is_interactive: bool = False,
        run_with_sudo_privileges: bool = False,
        run_as_root: bool = False,
        timeout: float | None = None,
        shutdown_event: Event | CompoundEvent | None = None,
        is_checked: bool = False,
    ) -> RunningProcess:
        docker_command, tag = self._assemble_docker_exec_args(
            command, cwd, secrets, is_interactive, run_as_root, run_with_sudo_privileges
        )
        with self._snapshot_guard.read_lock():
            process = run_background(
                docker_command,
                process_class=DockerRunningProcess,
                shutdown_event=shutdown_event,
                is_checked=is_checked,
                timeout=timeout,
                process_class_kwargs=dict(tag=tag, container_id=self.container_id),
                env={**os.environ, **{k: v.unwrap() if isinstance(v, Secret) else v for k, v in secrets.items()}},
            )
            process.wait_until_started()
            return process

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
        before_sleep=log_before_sleep,
    )
    @check_provider_health_on_failure
    def snapshot(self) -> LocalDockerImage:
        tag = f"{self.environment_prefix}{self.project_id}-snapshot:{generate_id()}"
        try:
            with self._snapshot_guard.write_lock():
                result = run_blocking(
                    command=["docker", "commit", self.container_id, tag],
                )
        except ProcessError as e:
            raise EnvironmentFailure(
                f"Failed to snapshot Docker container {self.container_id} to image {tag}: returncode={e.returncode}\nstderr={e.stderr}\nstdout={e.stdout}"
            ) from e
        image_id = DockerImageID(result.stdout.strip().split(":")[-1].strip())
        snapshot = LocalDockerImage(docker_image_tag=tag, image_id=image_id, project_id=self.project_id)
        if self._on_snapshot is not None:
            self._on_snapshot(snapshot, False)
        return snapshot

    def persist(self) -> None:
        pass

    @check_provider_health_on_failure
    def is_alive(self) -> bool:
        # Check if container is running
        with self._snapshot_guard.read_lock():
            result = run_blocking(
                command=["docker", "inspect", "-f", "{{.State.Running}}", self.container_id],
                is_checked=False,
            )
        return result.returncode == 0 and result.stdout.strip() == "true"

    @check_provider_health_on_failure
    def exists(self, path: str) -> bool:
        # TODO (from maciek): Hmm, on a side note, environment.exists should probably be capable of accepting pathlib.Path
        try:
            with self._snapshot_guard.read_lock():
                result = run_blocking(
                    command=[
                        "docker",
                        "exec",
                        "--user",
                        SCULPTOR_USER,
                        self.container_id,
                        "test",
                        "-e",
                        path,
                    ],
                    is_output_traced=False,
                    is_checked=False,
                )
            return result.returncode == 0
        except ProcessError as e:
            raise EnvironmentFailure("Failed to check if path exists because docker exec failed") from e

    # TODO: output typing should discriminate based on mode literals, or better yet we should have `read_binary_file` and `read_text_file` methods
    @check_provider_health_on_failure
    def read_file(self, path: str, mode: Union["OpenTextModeReading", "OpenBinaryModeReading"] = "r") -> str | bytes:
        try:
            with self._snapshot_guard.read_lock():
                result = run_blocking(
                    command=["docker", "exec", "--user", SCULPTOR_USER, self.container_id, "cat", path],
                    is_output_traced=False,
                )
        except ProcessError as e:
            raise FileNotFoundEnvironmentError(f"Failed to read file {path}: {e.stderr}") from e
        if "b" in mode:
            return result.stdout.encode("utf-8")
        return result.stdout

    @check_provider_health_on_failure
    def write_file(
        self,
        path: str,
        content: str | bytes,
        mode: str = "w",  # "w" or "a"; no binary support for now
        run_as_root: bool = False,
    ) -> None:
        assert mode in ("w", "a"), "w and a are the only supported modes"

        # Normalize to bytes
        data = content.encode("utf-8") if isinstance(content, str) else content

        parent_dir = str(Path(path).parent)
        q_parent = shlex.quote(parent_dir if parent_dir not in ("/", ".") else "/")
        q_path = shlex.quote(path)

        # Single exec: ensure dir exists, then stream to file
        redirector = ">" if mode == "w" else ">>"
        shell = f"mkdir -p {q_parent} && cat {redirector} {q_path}"

        cmd = ["docker", "exec", "-i"]
        if run_as_root:
            cmd += ["--user", "root"]
        else:
            cmd += ["--user", SCULPTOR_USER]
        cmd += [self.container_id, "sh", "-c", shell]
        with self._snapshot_guard.read_lock():
            # Note: run_blocking doesn't support stdin input, so we keep subprocess.run for this specific case
            result = subprocess.run(cmd, input=data, capture_output=True)
        if result.returncode != 0:
            raise EnvironmentFailure(
                f"Failed to write file {path} in container: returncode={result.returncode}\n"
                + f"stderr={result.stderr}\nstdout={result.stdout}"
            )

    def move_file(
        self,
        original_path: str,
        new_path: str,
        run_as_root: bool = False,
    ) -> None:
        cmd = ["docker", "exec"]
        if run_as_root:
            cmd += ["--user", "root"]
        cmd += [self.container_id, "mv", original_path, new_path]
        try:
            with self._snapshot_guard.read_lock():
                run_blocking(
                    command=cmd,
                )
        except ProcessError as e:
            raise FileNotFoundEnvironmentError(
                f"Failed to move file from {original_path} to {new_path}: {e.stderr}"
            ) from e

    def get_server_url(self, name: str) -> AnyUrl:
        server_port = self.server_port_by_name[name]
        return AnyUrl(f"http://localhost:{server_port}")

    def close(self) -> None:
        """Stop a Docker container."""
        logger.info("Stopping Docker container {}", self.container_id)
        try:
            stop_docker_container(container_id=self.container_id)
        except ProviderIsDownError:
            pass

    def destroy(self) -> None:
        """Stop and remove a Docker container."""
        logger.info("Destroying Docker container {}", self.container_id)
        remove_docker_container(container_id=self.container_id)

    @check_provider_health_on_failure
    def copy_from_local(self, local_path: Path, env_path: str, recursive: bool = True) -> None:
        if not local_path.exists():
            raise FileNotFoundEnvironmentError(f"Local path {local_path} does not exist")

        if local_path.is_dir() and not recursive:
            raise IsADirectoryEnvironmentError(f"{local_path} is a directory but recursive=False")

        # Ensure parent directory exists in container
        parent_dir = str(Path(env_path).parent)
        if parent_dir != "/" and parent_dir != ".":
            try:
                with self._snapshot_guard.read_lock():
                    run_blocking(
                        command=[
                            "docker",
                            "exec",
                            "--user",
                            SCULPTOR_USER,
                            self.container_id,
                            "mkdir",
                            "-p",
                            parent_dir,
                        ],
                        is_output_traced=False,
                    )
            except ProcessError as e:
                raise EnvironmentFailure(
                    f"Failed to create parent directory {parent_dir} in container: returncode={e.returncode}\nstderr={e.stderr}\nstdout={e.stdout}"
                ) from e

        # Use docker cp to copy the file/directory
        logger.info("Copying {} to {}:{}", local_path, self.container_id, env_path)
        try:
            with self._snapshot_guard.read_lock():
                cp_process = run_background(
                    command=["docker", "cp", str(local_path), f"{self.container_id}:{env_path}"],
                    is_checked=True,
                )
            cp_process.wait()
            with self._snapshot_guard.read_lock():
                chown_process = run_background(
                    command=[
                        "docker",
                        "exec",
                        "--user",
                        "root",
                        self.container_id,
                        "chown",
                        "-R",
                        f"{SCULPTOR_USER}:{SCULPTOR_USER}",
                        env_path,
                    ],
                    is_checked=True,
                )
            chown_process.wait()
        except ProcessError as e:
            raise EnvironmentFailure(
                f"Failed to copy {local_path} to container: returncode={e.returncode}\nstderr={e.stderr}\nstdout={e.stdout}"
            ) from e

    @check_provider_health_on_failure
    def copy_to_local(self, env_path: str, local_path: Path, recursive: bool = True) -> None:
        if not self.exists(env_path):
            raise FileNotFoundEnvironmentError(f"Path {env_path} does not exist in container")

        # Check if it's a directory
        is_dir_result = run_blocking(
            command=["docker", "exec", "--user", SCULPTOR_USER, self.container_id, "test", "-d", env_path],
            is_checked=False,
            is_output_traced=False,
        )
        is_directory = is_dir_result.returncode == 0

        if is_directory and not recursive:
            raise IsADirectoryEnvironmentError(f"{env_path} is a directory but recursive=False")

        # Ensure parent directory exists locally
        local_path.parent.mkdir(parents=True, exist_ok=True)

        # Use docker cp to copy from container
        logger.info("Copying {}:{} to {}", self.container_id, env_path, local_path)
        try:
            with self._snapshot_guard.read_lock():
                process = run_background(
                    command=["docker", "cp", f"{self.container_id}:{env_path}", str(local_path)],
                    is_checked=True,
                )
            process.wait()
        except ProcessError as e:
            raise EnvironmentFailure(
                f"Failed to copy {env_path} from container: returncode={e.returncode}\nstderr={e.stderr}\nstdout={e.stdout}"
            ) from e


def stop_docker_container(container_id: str) -> None:
    try:
        run_blocking(
            command=["docker", "stop", container_id],
            is_checked=True,
            is_output_traced=False,
        )
    except ProcessError as e:
        if "No such container" in e.stderr:
            logger.debug("Docker container {} already gone to stop it", container_id)
            return
        elif not isinstance(get_docker_status(), OkStatus):
            health_status = get_docker_status()
            if not isinstance(health_status, OkStatus):
                logger.debug("Docker seems to be down, cannot stop container {}", container_id)
                details_msg = f" (details: {health_status.details})" if health_status.details else ""
                raise ProviderIsDownError(f"Provider is unavailable: {health_status.message}{details_msg}") from e
            else:
                log_exception(
                    e,
                    "Failed to stop Docker container, but docker seems to be running...",
                    priority=ExceptionPriority.LOW_PRIORITY,
                    extra=dict(container_id=container_id),
                )


def remove_docker_container(container_id: str) -> None:
    logger.info("Removing outdated Docker container {}", container_id)
    try:
        run_blocking(
            command=["docker", "rm", "-f", container_id],
            timeout=30.0,
        )
    except ProcessError as e:
        # Error response from daemon: removal of container edcd0b869be5ed55902c9b6d45513e4a40e92ef6db4746ac53a554c0f10910dd is already in progress
        if e.stderr.strip().startswith(
            "Error response from daemon: removal of container"
        ) and e.stderr.strip().endswith("is already in progress"):
            logger.warning("Docker container {} is already being removed", container_id)
            return
        else:
            health_status = get_docker_status()
            if not isinstance(health_status, OkStatus):
                logger.debug("Docker seems to be down, cannot remote container {}", container_id)
                details_msg = f" (details: {health_status.details})" if health_status.details else ""
                raise ProviderIsDownError(f"Provider is unavailable: {health_status.message}{details_msg}") from e
            else:
                log_exception(
                    e,
                    "Failed to remove outdated Docker container",
                    priority=ExceptionPriority.LOW_PRIORITY,
                    extra=dict(container_id=container_id),
                )
