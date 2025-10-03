import json
from pathlib import Path
from threading import Lock
from typing import Mapping

from loguru import logger
from pydantic import PrivateAttr

from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.async_monkey_patches import log_exception
from imbue_core.common import generate_id
from imbue_core.constants import ExceptionPriority
from sculptor.interfaces.environments.v1.base import ImageConfig
from sculptor.interfaces.environments.v1.base import LocalDevcontainerImageConfig
from sculptor.interfaces.environments.v1.base import LocalDockerEnvironmentConfig
from sculptor.interfaces.environments.v1.base import LocalDockerImage
from sculptor.interfaces.environments.v1.errors import EnvironmentConfigurationChangedError
from sculptor.interfaces.environments.v1.provider_status import ProviderStatus
from sculptor.primitives.ids import DockerContainerID
from sculptor.services.environment_service.api import TaskImageCleanupData
from sculptor.services.environment_service.environments.docker_environment import DockerEnvironment
from sculptor.services.environment_service.environments.utils import get_docker_status
from sculptor.services.environment_service.providers.api import EnvironmentProvider
from sculptor.services.environment_service.providers.docker.devcontainer_image_builder import (
    build_local_devcontainer_image,
)
from sculptor.services.environment_service.providers.docker.environment_utils import build_docker_environment
from sculptor.services.environment_service.providers.docker.environment_utils import get_base_docker_create_args
from sculptor.services.environment_service.providers.docker.environment_utils import get_external_port_by_name_mapping
from sculptor.services.environment_service.providers.docker.environment_utils import setup_docker_environment
from sculptor.services.environment_service.providers.docker.environment_utils import start_docker_container
from sculptor.services.environment_service.providers.docker.environment_utils import stop_outdated_docker_containers
from sculptor.services.environment_service.providers.docker.errors import DockerError
from sculptor.services.environment_service.providers.docker.image_utils import DeletionTier
from sculptor.services.environment_service.providers.docker.image_utils import (
    delete_docker_image_and_any_stopped_containers,
)
from sculptor.services.environment_service.providers.docker.image_utils import get_image_ids_to_delete
from sculptor.startup_checks import check_docker_installed
from sculptor.startup_checks import check_docker_running
from sculptor.utils.build import get_sculptor_folder
from sculptor.utils.secret import Secret


def _save_container_id_data(previous_create_command_by_environment_id: dict[DockerContainerID, list[str]]) -> None:
    most_recent_data_path = get_sculptor_folder() / "providers" / "docker" / "container_ids.json"
    most_recent_data_path.parent.mkdir(parents=True, exist_ok=True)
    most_recent_data_path.with_suffix(".tmp").write_text(json.dumps(previous_create_command_by_environment_id))
    most_recent_data_path.with_suffix(".tmp").rename(most_recent_data_path)
    logger.trace("Wrote docker container id data to {}", most_recent_data_path)


def _load_container_id_data() -> dict[DockerContainerID, list[str]]:
    most_recent_data_path = get_sculptor_folder() / "providers" / "docker" / "container_ids.json"
    if most_recent_data_path.exists():
        try:
            return json.loads(most_recent_data_path.read_text())
        except FileNotFoundError:
            return {}
        except Exception as e:
            log_exception(e, "Failed to load container id data from {}", most_recent_data_path)
            return {}
    return {}


class DockerProvider(EnvironmentProvider):
    _previous_create_command_by_environment_id: dict[DockerContainerID, list[str]] = PrivateAttr(
        default_factory=_load_container_id_data
    )
    _previous_create_command_by_environment_id_lock: Lock = PrivateAttr(default_factory=Lock)

    def create_image(
        self,
        config: ImageConfig,
        project_id: ProjectID,
        secrets: Mapping[str, str | Secret],
        cached_repo_tarball_parent_directory: Path,
        environment_prefix: str,
    ) -> LocalDockerImage:
        if not isinstance(config, LocalDevcontainerImageConfig):
            raise ValueError(f"Invalid config type: {type(config)}")

        image_name = f"{environment_prefix}{project_id}"
        image_name_with_explicit_tag = f"{image_name}:{generate_id()}"
        image = build_local_devcontainer_image(
            config, cached_repo_tarball_parent_directory, project_id=project_id, tag=image_name_with_explicit_tag
        )
        return image

    def remove_stale_images(self, task_metadata_by_task_id: dict[str, TaskImageCleanupData]) -> tuple[str, ...]:
        image_ids_to_delete = get_image_ids_to_delete(task_metadata_by_task_id, DeletionTier.RARELY_DELETE)
        deleted_image_ids = []
        failed_image_ids = []
        deleted_container_ids: list[DockerContainerID] = []

        for image_id in image_ids_to_delete:
            is_deleted, new_deleted_image_ids = delete_docker_image_and_any_stopped_containers(image_id)
            deleted_container_ids.extend(new_deleted_image_ids)
            if is_deleted:
                deleted_image_ids.append(image_id)
            else:
                failed_image_ids.append(image_id)

        logger.debug("Successfully deleted {} Docker images", deleted_image_ids)
        if len(failed_image_ids) > 0:
            logger.debug("{} images failed to delete", failed_image_ids)

        # finally, adjust our saved state to remove any containers that were deleted
        with self._previous_create_command_by_environment_id_lock:
            for container_id in deleted_container_ids:
                if container_id in self._previous_create_command_by_environment_id:
                    del self._previous_create_command_by_environment_id[container_id]
            _save_container_id_data(self._previous_create_command_by_environment_id)

        logger.debug("Docker image cleanup completed")
        return tuple(deleted_image_ids)

    def get_default_environment_config(self) -> LocalDockerEnvironmentConfig:
        return LocalDockerEnvironmentConfig()

    def cleanup(self, environment_prefix: str) -> None:
        try:
            stop_outdated_docker_containers(environment_prefix)
        except DockerError as e:
            # only log the error if docker is installed and running
            if check_docker_installed() and check_docker_running():
                log_exception(e, "Failed to clean up docker containers", priority=ExceptionPriority.LOW_PRIORITY)

    def create_environment(
        self,
        image: LocalDockerImage,
        config: LocalDockerEnvironmentConfig,
        environment_prefix: str,
        name: str | None = None,
    ) -> DockerEnvironment:
        environment, create_command = build_docker_environment(
            docker_image=image,
            config=config,
            environment_prefix=environment_prefix,
            name=name,
            provider_health_check=self.get_status,
        )
        with self._previous_create_command_by_environment_id_lock:
            self._previous_create_command_by_environment_id[environment.environment_id] = create_command
            _save_container_id_data(self._previous_create_command_by_environment_id)
        return environment

    def start_environment(
        self,
        environment_id: DockerContainerID,
        project_id: ProjectID,
        config: LocalDockerEnvironmentConfig,
        environment_prefix: str,
        name: str | None = None,
    ) -> DockerEnvironment:
        create_command, group_id, user_id = get_base_docker_create_args(
            environment_prefix + name, config.server_port_by_name
        )
        with self._previous_create_command_by_environment_id_lock:
            previous_create_command = self._previous_create_command_by_environment_id.get(environment_id, None)
        if create_command != previous_create_command:
            raise EnvironmentConfigurationChangedError(
                f"The configuration has changed to {create_command} from {previous_create_command}"
            )
        start_docker_container(environment_id)
        external_port_by_name = get_external_port_by_name_mapping(environment_id, config.server_port_by_name)
        environment = DockerEnvironment(
            config=config,
            project_id=project_id,
            environment_id=DockerContainerID(environment_id),
            server_port_by_name=external_port_by_name,
            _provider_health_check=self.get_status,
            environment_prefix=environment_prefix,
        )
        setup_docker_environment(environment, group_id, user_id)
        return environment

    def get_status(self) -> ProviderStatus:
        """
        Get the current status of the Docker provider.

        Returns:
            ProviderStatus: The current status of the Docker provider.
        """
        return get_docker_status()
