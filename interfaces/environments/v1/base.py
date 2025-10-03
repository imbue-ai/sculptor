import abc
from abc import abstractmethod
from enum import StrEnum
from pathlib import Path
from threading import Event
from typing import Annotated
from typing import Callable
from typing import Mapping
from typing import Sequence
from typing import TYPE_CHECKING
from typing import Union

from pydantic import AnyUrl
from pydantic import BaseModel
from pydantic import Field
from pydantic import PrivateAttr
from pydantic import Tag
from typing_extensions import deprecated

from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.processes.local_process import RunningProcess
from imbue_core.pydantic_serialization import SerializableModel
from imbue_core.pydantic_serialization import build_discriminator
from imbue_core.subprocess_utils import CompoundEvent
from sculptor.constants import ROOT_PATH
from sculptor.interfaces.environments.v1.constants import ENVIRONMENT_WORKSPACE_DIRECTORY
from sculptor.interfaces.environments.v1.provider_status import ProviderStatus
from sculptor.primitives.ids import DockerImageID
from sculptor.primitives.ids import LocalImageID
from sculptor.primitives.ids import ModalImageObjectID
from sculptor.utils.secret import Secret

# https://github.com/python/typeshed/tree/main/stdlib/_typeshed
if TYPE_CHECKING:
    # for proper file mode typing
    from _typeshed import OpenBinaryModeReading
    from _typeshed import OpenBinaryModeWriting
    from _typeshed import OpenTextModeReading
    from _typeshed import OpenTextModeWriting


TTYD_SERVER_NAME = "terminal"
# This port actually points to an nginx proxy in front of ttyd that helps with auth.
# (It's hardcoded in claude-container/ttyd_nginx_proxy.conf.)
TTYD_SERVER_PORT = 80
SSHD_SERVER_NAME = "sshd"
SSHD_SERVER_PORT = 2222

STATE_DIRECTORY = "state"
ARTIFACTS_DIRECTORY = "artifacts"
CLAUDE_JSONL_DIRECTORY = ".claude/projects/./-code"


def _get_default_server_port_by_name() -> dict[str, int]:
    """Returns a default mapping of server names to ports."""
    return {TTYD_SERVER_NAME: TTYD_SERVER_PORT, SSHD_SERVER_NAME: SSHD_SERVER_PORT}


class ProviderTag(StrEnum):
    DOCKER = "DOCKER"
    MODAL = "MODAL"
    LOCAL = "LOCAL"


class ProviderResource(SerializableModel, abc.ABC):
    @abstractmethod
    def get_environment_tag(self) -> ProviderTag: ...


class EnvironmentConfig(ProviderResource, SerializableModel):
    # maps from the name of the service (ex: "terminal") to the port it should run on (inside the container)
    # note that currently, there is no guarantee that the port will be available on the host machine
    # (if there is an error, we simply report it and continue)
    # See note c70ca82b-f7b2-4beb-b2b4-0db777ad369b for more.
    server_port_by_name: dict[str, int] = Field(default_factory=dict)


class ModalEnvironmentConfig(EnvironmentConfig):
    object_type: str = "ModalEnvironmentConfig"
    server_port_by_name: dict[str, int] = Field(default_factory=_get_default_server_port_by_name)
    # Timeout for the sandbox (default 600 seconds/10 minutes)
    timeout: int = 600
    # GPU to mount (of any)
    # Valid values: "any", "a100", "a10g", "h100", "l4", "t4"
    # ref: https://modal.com/docs/reference/modal.gpu
    # If not None, will create a sandbox with one of the specified GPUs
    # It is also possible to specify multiple GPUs and also GPU memory (see docs)
    # Though this is not currently explicitly supported here
    gpu: str | None = None
    # How many CPU cores to request. This is a soft limit (containers can spike above this,
    # if there is free capacity on the worker).
    # default is 0.125 CPU cores
    # ref: https://modal.com/docs/guide/resources#reserving-cpu-and-memory
    cpu: float | None | tuple[float, float] = 1.0
    # Specify, in MiB, a memory request which is the minimum memory required.
    # Or, pass (request, limit) to additionally specify a hard limit in MiB.
    # If no hard limit is specified, containers can spike above minimum memory, if
    # there is free memory on the worker.
    # default is 128 MiB
    # ref: https://modal.com/docs/guide/resources#reserving-cpu-and-memory
    memory: int | tuple[int, int] | None = 4096
    # List of ports to expose from the container
    # This results in a tunnel being created that forwards the specified port to the local machine
    # ref: https://modal.com/docs/guide/tunnels
    exposed_ports: list[int] | None = None
    # unencrypted ports to expose, e.g. for SSH, Jupyter, etc.
    # ref: https://modal.com/docs/guide/tunnels
    unencrypted_ports: list[int] | None = None
    # Geographic region to run the sandbox in
    # ref: https://modal.com/docs/guide/region-selection#region-selection
    # FIXME: we need to be smarter about region selection
    #  For interactive terminals, we probably want them close to users
    #  However, it seems a bit flakier to run in particular regions, eg, us-west
    # region: str | Sequence[str] | None = "us-west"
    region: str | Sequence[str] | None = None
    cwd: str | None = None

    def get_environment_tag(self) -> ProviderTag:
        return ProviderTag.MODAL


class LocalDockerEnvironmentConfig(EnvironmentConfig):
    object_type: str = "LocalDockerEnvironmentConfig"
    server_port_by_name: dict[str, int] = Field(default_factory=_get_default_server_port_by_name)

    def get_environment_tag(self) -> ProviderTag:
        return ProviderTag.DOCKER


class LocalEnvironmentConfig(EnvironmentConfig):
    object_type: str = "LocalEnvironmentConfig"
    server_port_by_name: dict[str, int] = Field(
        # reset all default ports to 0 when running on the "local" provider because they will all run in a shared space
        # without this, you would only be able to run a single Environment at a time (the second would have port conflicts)
        default_factory=lambda: {k: 0 for k in _get_default_server_port_by_name().keys()}
    )

    def get_environment_tag(self) -> ProviderTag:
        return ProviderTag.LOCAL


EnvironmentConfigTypes = Annotated[
    Annotated[ModalEnvironmentConfig, Tag("ModalEnvironmentConfig")]
    | Annotated[LocalDockerEnvironmentConfig, Tag("LocalDockerEnvironmentConfig")]
    | Annotated[LocalEnvironmentConfig, Tag("LocalEnvironmentConfig")],
    build_discriminator(),
]


class VolumeConfig(ProviderResource, SerializableModel):
    pass


class Volume(ProviderResource, SerializableModel):
    pass


class ImageConfig(ProviderResource, SerializableModel):
    pass


class LocalImageConfig(ImageConfig):
    # This is written as a comment rather than docstring to avoid a schema change.
    # An "image" (not really) based on a directory on the local filesystem (stretches the definition of "image").

    object_type: str = "LocalImageConfig"
    code_directory: Path

    def get_environment_tag(self) -> ProviderTag:
        return ProviderTag.LOCAL


class ModalImageConfig(ImageConfig):
    object_type: str = "ModalImageConfig"
    dockerfile_path: str

    def get_environment_tag(self) -> ProviderTag:
        return ProviderTag.MODAL


@deprecated("Current code paths use LocalDevcontainerImageConfig instead.")
class LocalDockerImageConfig(ImageConfig):
    object_type: str = "LocalDockerImageConfig"
    dockerfile_path: str

    def get_environment_tag(self) -> ProviderTag:
        return ProviderTag.DOCKER


# TODO: THAD: It feels a little weird to have to repeat this for Modal.
class LocalDevcontainerImageConfig(ImageConfig):
    object_type: str = "LocalDevcontainerImageConfig"
    # Expected to point to a devcontainer.json file in the user's code tree that's visible to Sculptor.
    # TODO: THAD: This should be a Path, not a str?  But being consistent with above...
    devcontainer_json_path: str

    def get_environment_tag(self) -> ProviderTag:
        return ProviderTag.DOCKER


ImageConfigTypes = Annotated[
    Annotated[ModalImageConfig, Tag("ModalImageConfig")]
    | Annotated[LocalDockerImageConfig, Tag("LocalDockerImageConfig")]
    | Annotated[LocalImageConfig, Tag("LocalImageConfig")]
    | Annotated[LocalDevcontainerImageConfig, Tag("LocalDevcontainerImageConfig")],
    build_discriminator(),
]

ImageIDTypes = Annotated[
    Annotated[LocalImageID, Tag("LocalImageID")]
    | Annotated[ModalImageObjectID, Tag("ModalImageObjectID")]
    | Annotated[DockerImageID, Tag("DockerImageID")],
    build_discriminator(),
]


class Image(ProviderResource, SerializableModel):
    image_id: ImageIDTypes
    project_id: ProjectID


class LocalImage(Image):
    # This is written as a comment rather than docstring to avoid a schema change.
    # An "image" based on a directory on the local filesystem. It feels like a stretch to call this an image.

    object_type: str = "LocalImage"
    image_id: LocalImageID
    image_path: Path

    def get_environment_tag(self) -> ProviderTag:
        return ProviderTag.LOCAL


class ModalImage(Image):
    object_type: str = "ModalImage"
    image_id: ModalImageObjectID
    app_name: str

    def get_environment_tag(self) -> ProviderTag:
        return ProviderTag.MODAL


class LocalDockerImage(Image):
    object_type: str = "LocalDockerImage"
    image_id: DockerImageID
    docker_image_tag: str

    def get_environment_tag(self) -> ProviderTag:
        return ProviderTag.DOCKER


ImageTypes = Annotated[
    Annotated[LocalImage, Tag("LocalImage")]
    | Annotated[ModalImage, Tag("ModalImage")]
    | Annotated[LocalDockerImage, Tag("LocalDockerImage")],
    build_discriminator(),
]


# TODO: clean up this interface -- it has gotten needlessly messy
# TODO: rethink the way paths are done here - should we always assume absolute paths? relative paths?
# TODO: move the implementation off of this interface -- it should be fully abstract
# TODO: document the errors that can be raised by each method.
#  For example, both Environment's and Process's can always raise EnvironmentCrashed
#  because the environment can disappear at any time
class Environment(BaseModel, abc.ABC):
    environment_id: str
    project_id: ProjectID
    _provider_health_check: Callable[[], ProviderStatus] | None = PrivateAttr(default=None)
    _on_snapshot: Callable[[ImageTypes, bool], None] | None = PrivateAttr(default=None)

    def get_root_path(self) -> Path:
        """
        Get the root path inside the environment.

        All paths within the environment will be typically relative to this.

        """
        return ROOT_PATH

    def get_state_path(self) -> Path:
        return self.get_root_path() / STATE_DIRECTORY

    # TODO: this is unused
    def get_workspace_path(self) -> Path:
        return ENVIRONMENT_WORKSPACE_DIRECTORY

    def get_artifacts_path(self) -> Path:
        return self.get_root_path() / ARTIFACTS_DIRECTORY

    def get_claude_jsonl_path(self) -> Path:
        return self.get_root_path() / CLAUDE_JSONL_DIRECTORY

    def get_repo_url(self) -> AnyUrl:
        raise NotImplementedError("get_repo_url is not implemented for this environment")

    def push_into_environment_repo(self, user_repo_path: Path, src_branch_name: str, dst_branch_name: str) -> None:
        raise NotImplementedError("push_to_repo is not implemented for this environment")

    def get_repo_url_for_mutagen(self) -> str:
        raise NotImplementedError("get_repo_url_for_mutagen is not implemented for this environment")

    @abc.abstractmethod
    def get_file_mtime(self, path: str) -> float: ...

    def to_host_path(self, path: Path) -> Path:
        """
        Convert an absolute path to a path that is valid for shoving into a shell command that you want to execute in this environment.

        This will normally just return the input, except for local Environments, which simply prefix the path with their root folder.
        """
        return path

    def to_environment_path(self, path: Path) -> Path:
        """
        Does the reverse of convert_to_shell_path.
        """
        return path

    @abc.abstractmethod
    def get_config(self) -> EnvironmentConfigTypes: ...

    @abc.abstractmethod
    def get_extra_logger_context(self) -> Mapping[str, str | float | int | bool | None]: ...

    # Prefer running this through ConcurrencyGroup.run_environment_process_in_background if possible to avoid accidental leaks.
    @abc.abstractmethod
    def run_process_in_background(
        self,
        command: Sequence[str],
        secrets: Mapping[str, str | Secret],
        cwd: str | None = None,
        is_interactive: bool = False,
        run_with_sudo_privileges: bool = False,
        run_as_root: bool = False,
        shutdown_event: Event | CompoundEvent | None = None,
        timeout: float | None = None,
        is_checked: bool = False,
    ) -> RunningProcess: ...

    # Prefer running this through ConcurrencyGroup.run_environment_process_to_completion if possible to avoid accidental leaks.
    def run_process_to_completion(
        self,
        command: Sequence[str],
        secrets: Mapping[str, str | Secret],
        cwd: str | None = None,
        is_interactive: bool = False,
        run_with_sudo_privileges: bool = False,
        run_as_root: bool = False,
        timeout: float | None = None,
        is_checked: bool = True,
    ) -> RunningProcess:
        process = self.run_process_in_background(
            command,
            secrets,
            cwd,
            is_interactive,
            run_with_sudo_privileges,
            run_as_root,
            is_checked=is_checked,
            timeout=timeout,
        )
        process.wait()
        return process

    @abc.abstractmethod
    def snapshot(self) -> ImageTypes:
        """
        Snapshot the current state of the environment as a new image (from which you can fork new environments).
        """

    @abc.abstractmethod
    def persist(self) -> None:
        """
        Persist the environment, ensuring that all data is saved.

        This is a no-op for environments that are always persistent (e.g. local environments and docker containers).
        """

    @abc.abstractmethod
    def is_alive(self) -> bool: ...

    @abc.abstractmethod
    def exists(self, path: str) -> bool: ...

    @abc.abstractmethod
    def read_file(self, path: str, mode: Union["OpenTextModeReading", "OpenBinaryModeReading"] = "r") -> str | bytes:
        """
        Read a file from the environment.

        Raises:
            FileNotFoundEnvironmentError: if the file does not exist.
        """

    @abc.abstractmethod
    def write_file(
        self,
        path: str,
        content: str | bytes,
        mode: Union["OpenTextModeWriting", "OpenBinaryModeWriting"] = "w",
    ) -> None:
        """
        Write a file to the environment.

        Raises:
            EnvironmentFailure: if the file cannot be written.
        """

    @abc.abstractmethod
    def move_file(
        self,
        original_path: str,
        new_path: str,
    ) -> None:
        """
        Move a file to the new location in the environment.

        Raises:
            EnvironmentFailure: if the file cannot be moved.
        """

    @abc.abstractmethod
    def get_server_url(self, name: str) -> AnyUrl:
        """
        Gets the full server URL for the given service name.

        Note that the Environment will take care of encryption,
        but the caller is responsible for ensuring that the service does authentication and authorization correctly.
        Environment server URLs may be publicly accessible!
        """

    @abc.abstractmethod
    def close(self) -> None:
        """
        Close the environment, leaving it in a state where it can be opened again.

        In particular, all processes must be stopped, and all ephemeral data must be cleaned up.

        Volumes and images will not be deleted, as they may be reused in the future.
        """

    @abc.abstractmethod
    def destroy(self) -> None:
        """
        Destroy the environment, releasing any resources it holds.

        In particular, any persistent containers will be delete, as well as any volumes that were only used by this environment.

        This calls close() as well, eg, is a superset of that cleanup behavior.
        """

    @abc.abstractmethod
    def copy_from_local(self, local_path: Path, env_path: str, recursive: bool = True) -> None:
        """
        Copy files or directories from the local filesystem into the environment.

        Args:
            local_path: Path on the local filesystem to copy from.
            env_path: Destination path inside the environment.
            recursive: If True, recursively copy directories. If False, only copy files.

        Raises:
            FileNotFoundError: If the local path does not exist.
            IsADirectoryError: If local_path is a directory and recursive is False.
            EnvironmentError: If the copy operation fails.
        """
        ...

    @abc.abstractmethod
    def copy_to_local(self, env_path: str, local_path: Path, recursive: bool = True) -> None:
        """
        Copy files or directories from the environment to the local filesystem.

        Args:
            env_path: Source path inside the environment.
            local_path: Destination path on the local filesystem.
            recursive: If True, recursively copy directories. If False, only copy files.

        Raises:
            FileNotFoundError: If the environment path does not exist.
            IsADirectoryError: If env_path is a directory and recursive is False.
            EnvironmentError: If the copy operation fails.
        """
