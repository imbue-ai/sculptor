from abc import ABC
from abc import abstractmethod
from pathlib import Path
from typing import Mapping

from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.pydantic_serialization import MutableModel
from sculptor.interfaces.environments.v1.base import Environment
from sculptor.interfaces.environments.v1.base import EnvironmentConfig
from sculptor.interfaces.environments.v1.base import Image
from sculptor.interfaces.environments.v1.base import ImageConfig
from sculptor.interfaces.environments.v1.provider_status import ProviderStatus
from sculptor.primitives.ids import EnvironmentIDTypes
from sculptor.services.environment_service.api import TaskImageCleanupData
from sculptor.utils.secret import Secret


class EnvironmentProvider(MutableModel, ABC):
    @abstractmethod
    def create_image(
        self,
        config: ImageConfig,
        project_id: ProjectID,
        secrets: Mapping[str, str | Secret],
        cached_repo_tarball_parent_directory: Path,
        environment_prefix: str,
    ) -> Image:
        """
        Create an image based on the given configuration and secrets.

        Raises:
            ProviderError: if provider is misconfigured, unavailable, etc.
            ImageConfigError: if image config or Dockerfile is invalid
        """

    @abstractmethod
    def remove_stale_images(self, task_metadata_by_task_id: dict[str, TaskImageCleanupData]) -> tuple[str, ...]:
        """
        Remove stale images based on the provided prefix and active tags.

        Returns:
            Tuple of successfully deleted image IDs
        """

    @abstractmethod
    def create_environment(
        self,
        image: Image,
        config: EnvironmentConfig,
        environment_prefix: str,
        name: str | None = None,
    ) -> Environment:
        """
        Generate an environment based on the given image.

        Raises:
            ProviderError: if provider is misconfigured, unavailable, etc.
            ImageConfigError: if image config is invalid
            SetupError: if the setup commands fail to run
        """

    @abstractmethod
    def start_environment(
        self,
        environment_id: EnvironmentIDTypes,
        project_id: ProjectID,
        config: EnvironmentConfig,
        environment_prefix: str,
        name: str | None = None,
    ) -> Environment:
        """
        Start a previously created Environment based on the given environment ID.

        Raises:
            ProviderError: if provider is misconfigured, unavailable, etc.
            ImageConfigError: if image config is invalid
            SetupError: if the setup commands fail to run
        """

    @abstractmethod
    def get_default_environment_config(self) -> EnvironmentConfig: ...

    @abstractmethod
    def cleanup(self, environment_prefix: str): ...

    @abstractmethod
    def get_status(self) -> ProviderStatus:
        """
        Get the current status of the provider.

        Returns:
            ProviderStatus: The current status of the provider.
        """
        ...
