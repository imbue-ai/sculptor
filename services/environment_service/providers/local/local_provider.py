import shutil
from pathlib import Path
from typing import Mapping

from loguru import logger

from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.async_monkey_patches import log_exception
from imbue_core.constants import ExceptionPriority
from imbue_core.subprocess_utils import ProcessError
from sculptor.interfaces.environments.v1.base import LocalEnvironmentConfig
from sculptor.interfaces.environments.v1.base import LocalImage
from sculptor.interfaces.environments.v1.base import LocalImageConfig
from sculptor.interfaces.environments.v1.provider_status import OkStatus
from sculptor.interfaces.environments.v1.provider_status import ProviderStatus
from sculptor.primitives.ids import LocalEnvironmentID
from sculptor.services.environment_service.api import TaskImageCleanupData
from sculptor.services.environment_service.environments.local_environment import LocalEnvironment
from sculptor.services.environment_service.providers.api import EnvironmentProvider
from sculptor.services.environment_service.providers.local.environment_utils import build_local_environment
from sculptor.services.environment_service.providers.local.environment_utils import (
    get_local_environment_sandbox_directory,
)
from sculptor.services.environment_service.providers.local.image_utils import build_local_image
from sculptor.utils.secret import Secret


class LocalProvider(EnvironmentProvider):
    def create_image(
        self,
        config: LocalImageConfig,
        project_id: ProjectID,
        secrets: Mapping[str, str | Secret],
        cached_repo_tarball_parent_directory: Path,
        environment_prefix: str,
    ) -> LocalImage:
        return build_local_image(code_directory=config.code_directory, project_id=project_id)

    def remove_stale_images(self, task_metadata_by_task_id: dict[str, TaskImageCleanupData]) -> tuple[str, ...]:
        # No image cleanup needed for local provider
        return ()

    def create_environment(
        self,
        image: LocalImage,
        config: LocalEnvironmentConfig,
        environment_prefix: str,
        name: str | None = None,
    ) -> LocalEnvironment:
        return build_local_environment(
            local_image=image,
            config=config,
            environment_prefix=environment_prefix,
            provider_health_check=self.get_status,
        )

    def start_environment(
        self,
        environment_id: LocalEnvironmentID,
        project_id: ProjectID,
        config: LocalEnvironmentConfig,
        environment_prefix: str,
        name: str | None = None,
    ) -> LocalEnvironment:
        return LocalEnvironment(
            environment_id=LocalEnvironmentID(str(environment_id)),
            project_id=project_id,
            config=config,
            _provider_health_check=self.get_status,
        )

    def get_default_environment_config(self) -> LocalEnvironmentConfig:
        return LocalEnvironmentConfig()

    def cleanup(self, environment_prefix: str):
        try:
            cleanup_outdated_local_sandboxes(environment_prefix)
        except ProcessError as e:
            log_exception(e, "Failed to clean up local sandboxes", priority=ExceptionPriority.LOW_PRIORITY)

    def get_status(self) -> ProviderStatus:
        """
        Get the current status of the Local provider.

        Returns:
            ProviderStatus: The current status of the Local provider.
        """
        return OkStatus(message="Local is available")


def cleanup_outdated_local_sandboxes(environment_prefix: str) -> None:
    environment_sandbox_directory = get_local_environment_sandbox_directory(environment_prefix)
    if not environment_sandbox_directory.exists():
        return
    for sandbox in environment_sandbox_directory.iterdir():
        if sandbox.is_dir() and not sandbox.name.startswith("."):
            logger.info("Cleaning up outdated local sandbox: {}", sandbox)
            shutil.rmtree(sandbox, ignore_errors=True)
