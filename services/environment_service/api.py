from abc import ABC
from abc import abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import Generator
from typing import Mapping

from pydantic import BaseModel

from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.agents.data_types.ids import TaskID
from sculptor.interfaces.environments.v1.base import Environment
from sculptor.interfaces.environments.v1.base import EnvironmentConfig
from sculptor.interfaces.environments.v1.base import Image
from sculptor.interfaces.environments.v1.base import ImageConfig
from sculptor.interfaces.environments.v1.base import ImageTypes
from sculptor.interfaces.environments.v1.base import ProviderTag
from sculptor.interfaces.environments.v1.provider_status import ProviderStatus
from sculptor.primitives.service import Service
from sculptor.utils.secret import Secret


class TaskImageCleanupData(BaseModel):
    task_id: TaskID
    last_image_id: str
    is_deleted: bool
    is_archived: bool
    all_image_ids: tuple[str, ...] = ()  # NOTE: all image ids only includes snapshots and not the base image


# TODO: we need to consider the process for Image and Volume deletion
# TODO: document the exceptions that can be raised by each of these methods
class EnvironmentService(Service, ABC):
    """
    This services enables robust environment creation and destruction via "structured concurrency".

    This means that, when you exit the context manager for a given environment, it will always be cleaned up properly,

    This service will automatically clean up any previous environments when it is started.
    This is required for correctness in the face of hard crashes or unexpected shutdowns.
    """

    @abstractmethod
    def ensure_image(
        self,
        config: ImageConfig,
        project_id: ProjectID,
        secrets: Mapping[str, str | Secret],
        active_repo_path: Path,
        cached_repo_path: Path,
    ) -> ImageTypes:
        """
        Get a cached image or create an image based on the given configuration and secrets.

        Raises:
            ProviderError: if provider is misconfigured, unavailable, etc.
            ImageConfigError: if image config or Dockerfile is invalid
        """

    @abstractmethod
    def remove_stale_images(self) -> tuple[str, ...]:
        """
        Remove stale images from each provider.

        Returns:
            Tuple of successfully deleted image IDs
        """

    @abstractmethod
    @contextmanager
    def generate_environment(
        self,
        image: Image,
        project_id: ProjectID,
        config: EnvironmentConfig | None = None,
        name: str | None = None,
    ) -> Generator[Environment, None, None]:
        """
        Generate an environment based on the given image.

        The environment will be cleaned up when the context manager exits.

        Raises:
            ProviderError: if provider is misconfigured, unavailable, etc.
            ImageConfigError: if image config is invalid
            SetupError: if the setup commands fail to run
        """

    @abstractmethod
    def create_environment(
        self,
        source: Image | str,
        project_id: ProjectID,
        config: EnvironmentConfig | None = None,
        name: str | None = None,
    ) -> Environment:
        """
        Create an environment based on the given image or environment ID

        Raises:
            ProviderError: if provider is misconfigured, unavailable, etc.
            ImageConfigError: if image config is invalid
            SetupError: if the setup commands fail to run
        """

    @abstractmethod
    def get_provider_statuses(self) -> dict[ProviderTag, ProviderStatus]:
        """
        Get the status of each provider.
        """
