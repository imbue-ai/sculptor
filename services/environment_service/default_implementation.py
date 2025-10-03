import hashlib
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from shutil import rmtree
from threading import Lock
from typing import Generator
from typing import Mapping

from pydantic import PrivateAttr
from pydantic import model_validator

from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.agents.data_types.ids import TaskID
from imbue_core.processes.local_process import run_blocking
from sculptor.config.settings import SculptorSettings
from sculptor.database.models import AgentTaskStateV1
from sculptor.database.models import Task
from sculptor.interfaces.agents.v1.agent import AgentSnapshotRunnerMessage
from sculptor.interfaces.environments.v1.base import Environment
from sculptor.interfaces.environments.v1.base import EnvironmentConfig
from sculptor.interfaces.environments.v1.base import Image
from sculptor.interfaces.environments.v1.base import ImageConfig
from sculptor.interfaces.environments.v1.base import LocalDockerEnvironmentConfig
from sculptor.interfaces.environments.v1.base import LocalDockerImage
from sculptor.interfaces.environments.v1.base import LocalEnvironmentConfig
from sculptor.interfaces.environments.v1.base import ModalEnvironmentConfig
from sculptor.interfaces.environments.v1.base import ProviderTag
from sculptor.interfaces.environments.v1.errors import ProviderNotFoundError
from sculptor.interfaces.environments.v1.provider_status import ProviderStatus
from sculptor.services.data_model_service.api import DataModelService
from sculptor.services.data_model_service.api import TaskDataModelService
from sculptor.services.environment_service.api import EnvironmentService
from sculptor.services.environment_service.api import TaskImageCleanupData
from sculptor.services.environment_service.providers.api import EnvironmentProvider
from sculptor.services.environment_service.providers.docker.devcontainer_image_builder import (
    start_control_plane_background_setup,
)
from sculptor.services.environment_service.providers.docker.docker_provider import DockerProvider
from sculptor.services.environment_service.providers.local.local_provider import LocalProvider
from sculptor.services.environment_service.providers.modal.modal_provider import ModalProvider
from sculptor.services.git_repo_service.api import GitRepoService
from sculptor.utils.secret import Secret
from sculptor.utils.timeout import log_runtime


def get_standard_environment_prefix(settings: SculptorSettings) -> str:
    return f"sculptor-{hashlib.sha256(settings.DATABASE_URL.encode()).hexdigest()}-"


def create_archived_repo(active_repo_path: Path, cached_tarball_path: Path) -> None:
    cached_tarball_parent = cached_tarball_path.parent
    if cached_tarball_parent.exists():
        rmtree(cached_tarball_parent)
    cached_tarball_parent.mkdir(parents=True, exist_ok=True)

    # Get all files that are not gitignored (tracked + untracked)
    result = run_blocking(
        ["git", "ls-files", "-z", "--cached", "--exclude-standard"],
        cwd=active_repo_path,
    )
    files_to_include = result.stdout.strip().split("\0") if result.stdout.strip() else []

    # Add the big things in the .git directory, preserving mtimes. We later use a one-way Mutagen
    # sync to bring the rest of .git up to date quickly.
    files_to_include.append(".git/objects")
    files_to_include.append(".git/refs")
    files_to_include.append(".git/logs")

    # Create tarball with all non-gitignored files plus .git directory
    if files_to_include:
        new_env = os.environ.copy()
        new_env["COPYFILE_DISABLE"] = "1"
        # Write files to temporary file for --files-from flag
        with tempfile.NamedTemporaryFile("w") as temp_file:
            temp_file.writelines(file + "\n" for file in files_to_include)
            temp_file.flush()
            temp_file_path = temp_file.name
            run_blocking(
                ["tar", "-cf", str(cached_tarball_path), "--files-from", temp_file_path],
                cwd=active_repo_path,
                env=new_env,
            )


class DefaultEnvironmentService(EnvironmentService):
    settings: SculptorSettings
    git_repo_service: GitRepoService
    data_model_service: DataModelService
    _is_started: bool = PrivateAttr(default=False)

    _providers: dict[ProviderTag, EnvironmentProvider] = PrivateAttr()
    _image_lock: Lock = PrivateAttr(default_factory=Lock)

    @model_validator(mode="after")
    def init_providers(self) -> "DefaultEnvironmentService":
        providers = {}
        if self.settings.DOCKER_PROVIDER_ENABLED:
            providers[ProviderTag.DOCKER] = DockerProvider()
            start_control_plane_background_setup(thread_suffix="EnvServiceInit")
        if self.settings.MODAL_PROVIDER_ENABLED:
            providers[ProviderTag.MODAL] = ModalProvider()
        if self.settings.LOCAL_PROVIDER_ENABLED:
            providers[ProviderTag.LOCAL] = LocalProvider()
        self._providers = providers
        return self

    # TODO: consider what should happen when there are errors from the provider during startup
    #  They may be transient or permanent, and it's a bit hard to tell
    #  In one sense, we may want to consider them disabled, but if it's only transient, that will be annoying.
    def start(self) -> None:
        self._is_started = True
        with log_runtime("cleaning up docker containers"):
            self._cleanup()

    def stop(self) -> None:
        self._cleanup()
        self._is_started = False

    def ensure_image(
        self,
        config: ImageConfig,
        project_id: ProjectID,
        secrets: Mapping[str, str | Secret],
        active_repo_path: Path,
        cached_repo_path: Path,
    ) -> Image:
        with self._image_lock:
            provider = self._get_provider(environment_tag=config.get_environment_tag())
            with log_runtime("Creating repo tarball"):
                cached_tarball_location = cached_repo_path / "repo.tar"
                if not cached_tarball_location.exists():
                    create_archived_repo(active_repo_path, cached_tarball_location)
            return provider.create_image(
                config=config,
                secrets=secrets,
                cached_repo_tarball_parent_directory=cached_repo_path,
                environment_prefix=self._environment_prefix,
                project_id=project_id,
            )

    def remove_stale_images(self) -> tuple[str, ...]:
        with self._image_lock:
            task_metadata_by_task_id = _get_task_metadata(self.data_model_service)
            all_deleted_images = []
            for provider in self._providers.values():
                deleted_images = provider.remove_stale_images(task_metadata_by_task_id)
                all_deleted_images.extend(deleted_images)
            return tuple(all_deleted_images)

    @contextmanager
    def generate_environment(
        self,
        image: Image,
        project_id: ProjectID,
        name: str | None = None,
        config: EnvironmentConfig | None = None,
    ) -> Generator[Environment, None, None]:
        environment = self.create_environment(source=image, name=name, config=config, project_id=project_id)
        try:
            yield environment
        finally:
            environment.close()

    def create_environment(
        self,
        source: Image | str,
        project_id: ProjectID,
        config: EnvironmentConfig | None = None,
        name: str | None = None,
    ) -> Environment:
        if isinstance(source, Image):
            provider = self._get_provider(environment_tag=source.get_environment_tag())
            if config is None:
                config = provider.get_default_environment_config()
            return provider.create_environment(
                image=source, name=name, config=config, environment_prefix=self._environment_prefix
            )
        else:
            if isinstance(config, ModalEnvironmentConfig):
                provider = self._get_provider(environment_tag=ProviderTag.MODAL)
            elif isinstance(config, LocalDockerEnvironmentConfig):
                provider = self._get_provider(environment_tag=ProviderTag.DOCKER)
            elif isinstance(config, LocalEnvironmentConfig) or config is None:
                provider = self._get_provider(environment_tag=ProviderTag.LOCAL)
            else:
                raise ProviderNotFoundError(f"Could not find provider for environment config of type '{type(config)}'")
            return provider.start_environment(
                environment_id=source,
                name=name,
                config=config,
                environment_prefix=self._environment_prefix,
                project_id=project_id,
            )

    def _get_provider(self, environment_tag: ProviderTag) -> EnvironmentProvider:
        provider = self._providers.get(environment_tag)
        if provider is None:
            raise ProviderNotFoundError(f"Could not find provider of type '{environment_tag}'")
        return provider

    def _cleanup(self) -> None:
        if self._is_started:
            for provider in self._providers.values():
                provider.cleanup(environment_prefix=self._environment_prefix)

    @property
    def _environment_prefix(self) -> str:
        if self.settings.TESTING.CONTAINER_PREFIX is not None:
            return f"{self.settings.TESTING.CONTAINER_PREFIX}-"
        return f"{get_standard_environment_prefix(self.settings)}"

    def get_provider_statuses(self) -> dict[ProviderTag, ProviderStatus]:
        """
        Get the status of each provider.

        Returns:
            dict[ProviderTag, ProviderStatus]: A mapping of provider tags to their statuses.
        """
        statuses = {}
        for provider_tag, provider in self._providers.items():
            statuses[provider_tag] = provider.get_status()
        return statuses


def _get_task_metadata(sql_service: TaskDataModelService) -> dict[TaskID, TaskImageCleanupData]:
    with sql_service.open_task_transaction() as transaction:
        # pyre-fixme[16]: get_all_tasks is only implemented by SQLTransaction, but transaction is TaskAndModelTransaction
        all_tasks: tuple[Task, ...] = transaction.get_all_tasks()

        task_metadata_by_task_id: dict[str, TaskImageCleanupData] = dict()
        for task in all_tasks:
            if isinstance(task.current_state, AgentTaskStateV1):
                saved_agent_messages = transaction.get_messages_for_task(task.object_id)
                snapshot_messages = [
                    message.message
                    for message in saved_agent_messages
                    if isinstance(message.message, AgentSnapshotRunnerMessage)
                ]
                all_image_ids = tuple(
                    message.image.image_id
                    for message in snapshot_messages
                    if isinstance(message.image, LocalDockerImage)
                )
                task_metadata = TaskImageCleanupData(
                    task_id=task.object_id,
                    last_image_id=task.current_state.image.image_id,
                    is_deleted=task.is_deleted or task.is_deleting,
                    is_archived=task.is_archived,
                    all_image_ids=all_image_ids,
                )
                task_metadata_by_task_id[task.object_id] = task_metadata

        return task_metadata_by_task_id
