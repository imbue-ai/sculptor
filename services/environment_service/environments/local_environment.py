import os
import shutil
import threading
from pathlib import Path
from typing import Mapping
from typing import Sequence
from typing import TYPE_CHECKING
from typing import Union

from loguru import logger
from pydantic import AnyUrl
from pydantic import PrivateAttr

from imbue_core.common import generate_id
from imbue_core.processes.local_process import RunningProcess
from imbue_core.processes.local_process import run_background
from sculptor.interfaces.environments.v1.base import Environment
from sculptor.interfaces.environments.v1.base import LocalEnvironmentConfig
from sculptor.interfaces.environments.v1.base import LocalImage
from sculptor.interfaces.environments.v1.base import ProviderTag
from sculptor.interfaces.environments.v1.errors import FileNotFoundEnvironmentError
from sculptor.primitives.ids import LocalEnvironmentID
from sculptor.primitives.ids import LocalImageID
from sculptor.services.environment_service.environments.utils import check_provider_health_on_failure
from sculptor.services.environment_service.providers.local.constants import LOCAL_SANDBOX_DIR
from sculptor.tasks.handlers.run_agent.git import run_git_command_local
from sculptor.utils.build import get_sculptor_folder
from sculptor.utils.file_utils import copy_dir
from sculptor.utils.secret import Secret

if TYPE_CHECKING:
    from _typeshed import OpenBinaryModeReading
    from _typeshed import OpenBinaryModeWriting
    from _typeshed import OpenTextModeReading
    from _typeshed import OpenTextModeWriting


class LocalEnvironment(Environment):
    object_type: str = "LocalEnvironment"
    environment_id: LocalEnvironmentID
    config: LocalEnvironmentConfig
    _processes: list[RunningProcess] = PrivateAttr(default_factory=list)
    _is_closed: bool = PrivateAttr(default=False)
    _closing_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)

    @property
    def sandbox_path(self) -> str:
        return self.environment_id

    def get_sandbox_path(self) -> Path:
        return Path(self.sandbox_path)

    def get_base_snapshot_folder(self) -> Path:
        base_snapshot_folder = get_sculptor_folder() / "local_environment_snapshots"
        base_snapshot_folder.mkdir(parents=True, exist_ok=True)
        return base_snapshot_folder

    def get_repo_url(self) -> AnyUrl:
        return AnyUrl(f"file://{self.to_host_path(self.get_workspace_path())}")

    def get_file_mtime(self, path: str) -> float:
        return (self.get_sandbox_path() / path.lstrip("/")).stat().st_mtime

    def to_host_path(self, path: Path) -> Path:
        assert path.is_absolute()
        return self.get_sandbox_path() / str(path).lstrip("/")

    def to_environment_path(self, path: Path) -> Path:
        assert path.is_absolute()
        root_path_str = str(self.get_sandbox_path())
        assert str(path).startswith(root_path_str)
        return Path("/" + str(path)[len(root_path_str) :].lstrip("/"))

    def get_extra_logger_context(self) -> Mapping[str, str | float | int | bool | None]:
        return {"sandbox_path": self.sandbox_path, "provider": ProviderTag.LOCAL}

    def get_config(self) -> LocalEnvironmentConfig:
        return self.config

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
        shutdown_event: threading.Event | None = None,
        is_checked: bool = False,
    ) -> RunningProcess:
        if run_with_sudo_privileges or run_as_root:
            raise NotImplementedError()

        env = {**os.environ, **{k: v.unwrap() if isinstance(v, Secret) else v for k, v in secrets.items()}}
        logger.info("Launching process: {} in sandbox: {}", (" ".join(command))[:50], self.sandbox_path)
        logger.trace("Launching process: {}", " ".join(command))
        workdir = self.to_host_path(Path(cwd) if cwd else self.get_workspace_path())
        process = run_background(
            command,
            cwd=workdir,
            env={k: str(v) for k, v in env.items() if v is not None},
            is_checked=is_checked,
            timeout=timeout,
            shutdown_event=shutdown_event,
        )
        self._processes.append(process)
        return process

    @check_provider_health_on_failure
    def snapshot(self) -> LocalImage:
        snapshot_location = self.get_base_snapshot_folder() / (generate_id())
        assert not snapshot_location.exists()
        copy_dir(self.get_sandbox_path(), snapshot_location)
        snapshot = LocalImage(image_id=LocalImageID(), image_path=snapshot_location, project_id=self.project_id)
        if self._on_snapshot is not None:
            self._on_snapshot(snapshot, False)
        return snapshot

    def persist(self) -> None:
        pass

    @check_provider_health_on_failure
    def is_alive(self) -> bool:
        # Local sandboxes are always "alive" as long as the directory exists
        return Path(self.sandbox_path).exists()

    @check_provider_health_on_failure
    def exists(self, path: str) -> bool:
        file_path = Path(self.sandbox_path) / path.lstrip("/")
        return file_path.exists()

    @check_provider_health_on_failure
    def read_file(self, path: str, mode: Union["OpenTextModeReading", "OpenBinaryModeReading"] = "r") -> str | bytes:
        file_path = Path(self.sandbox_path) / path.lstrip("/")
        with open(file_path, mode) as f:
            return f.read()

    @check_provider_health_on_failure
    def write_file(
        self,
        path: str,
        content: str | bytes,
        mode: Union["OpenTextModeWriting", "OpenBinaryModeWriting"] = "w",
    ) -> None:
        file_path = Path(self.sandbox_path) / path.lstrip("/")
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, mode) as f:
            f.write(content)

    def move_file(
        self,
        original_path: str,
        new_path: str,
    ) -> None:
        try:
            shutil.move(original_path, new_path)
        except OSError as e:
            raise FileNotFoundEnvironmentError(f"Failed to move file from {original_path} to {new_path}: {e}") from e

    def get_server_url(self, name: str) -> AnyUrl:
        internal_port = self.config.server_port_by_name[name]
        # FIXME: this doesn't work if you run more than one local environment at a time!
        return AnyUrl(f"http://localhost:{internal_port}")

    def close(self) -> None:
        with self._closing_lock:
            if self._is_closed:
                return
            logger.info("Stopping all processes for LocalEnvironment")
            for process in self._processes:
                try:
                    if process.poll() is None:
                        process.terminate()
                except Exception as e:
                    logger.warning(f"Failed to terminate process: {e}")
            # need to join all threads as well
            for process in self._processes:
                try:
                    process.wait()
                except Exception as e:
                    logger.warning(f"Failed to wait for process: {e}")
            self._is_closed = True

    def destroy(self) -> None:
        self.close()
        with self._closing_lock:
            remove_local_environment(Path(self.sandbox_path))

    @check_provider_health_on_failure
    def copy_from_local(self, local_path: Path, env_path: str, recursive: bool = True) -> None:
        if not local_path.exists():
            raise FileNotFoundError(f"Local path {local_path} does not exist")

        if local_path.is_dir() and not recursive:
            raise IsADirectoryError(f"{local_path} is a directory but recursive=False")

        dest_path = Path(self.sandbox_path) / env_path.lstrip("/")

        try:
            if local_path.is_file():
                # Create parent directories if needed
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                logger.info("Copying file {} to {}", local_path, dest_path)
                shutil.copy2(local_path, dest_path)
            else:
                # Copy directory
                logger.info("Copying directory {} to {}", local_path, dest_path)
                if dest_path.exists():
                    # If destination exists, copy contents into it
                    copy_dir(local_path, dest_path / local_path.name, dirs_exist_ok=True)
                else:
                    # If destination doesn't exist, create it with source contents
                    copy_dir(local_path, dest_path)
        except Exception as e:
            raise EnvironmentError(f"Failed to copy {local_path} to sandbox: {str(e)}")

    @check_provider_health_on_failure
    def copy_to_local(self, env_path: str, local_path: Path, recursive: bool = True) -> None:
        src_path = Path(self.sandbox_path) / env_path.lstrip("/")

        if not src_path.exists():
            raise FileNotFoundError(f"Path {env_path} does not exist in sandbox")

        if src_path.is_dir() and not recursive:
            raise IsADirectoryError(f"{env_path} is a directory but recursive=False")

        try:
            if src_path.is_file():
                # Create parent directories if needed
                local_path.parent.mkdir(parents=True, exist_ok=True)
                logger.info("Copying file {} to {}", src_path, local_path)
                shutil.copy2(src_path, local_path)
            else:
                # Copy directory
                logger.info("Copying directory {} to {}", src_path, local_path)
                if local_path.exists():
                    # If destination exists, copy contents into it
                    copy_dir(src_path, local_path / src_path.name, dirs_exist_ok=True)
                else:
                    # If destination doesn't exist, create it with source contents
                    copy_dir(src_path, local_path)
        except Exception as e:
            raise EnvironmentError(f"Failed to copy {env_path} from sandbox: {str(e)}")

    def push_into_environment_repo(self, user_repo_path: Path, src_branch_name: str, dst_branch_name: str) -> None:
        run_git_command_local(
            ["bash", "-c", f"git push --no-verify {self.get_repo_url()} {src_branch_name}:{dst_branch_name}"],
            cwd=user_repo_path,
            check_output=True,
            is_retry_safe=False,
        )


# TODO: we could be slightly smarter about the process ids that we launch, and thus make this robust enough to actually be usable in the product...
def stop_local_environment(sandbox_path: Path) -> None:
    pass


def remove_local_environment(sandbox_path: Path) -> None:
    logger.info("Deleting sandbox path {}", sandbox_path)
    sandbox_path = sandbox_path.resolve()
    # Resolve LOCAL_SANDBOX_DIR as well to handle macOS symlinks
    local_sandbox_dir_resolved = LOCAL_SANDBOX_DIR.resolve()
    assert len(str(local_sandbox_dir_resolved)) > 3, "Just double checking that you're not deleting your root dir"
    if not sandbox_path.is_relative_to(local_sandbox_dir_resolved):
        raise RuntimeError(f"Refusing to delete sandbox path {sandbox_path} outside of {local_sandbox_dir_resolved}")
    shutil.rmtree(sandbox_path, ignore_errors=True)
