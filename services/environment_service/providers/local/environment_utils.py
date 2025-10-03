import shutil
from pathlib import Path
from typing import Callable
from uuid import uuid4

from loguru import logger

from sculptor.interfaces.environments.v1.base import LocalEnvironmentConfig
from sculptor.interfaces.environments.v1.base import LocalImage
from sculptor.interfaces.environments.v1.provider_status import ProviderStatus
from sculptor.primitives.ids import LocalEnvironmentID
from sculptor.services.environment_service.environments.local_environment import LocalEnvironment
from sculptor.services.environment_service.environments.local_environment import remove_local_environment
from sculptor.services.environment_service.environments.local_environment import stop_local_environment
from sculptor.services.environment_service.providers.local.constants import LOCAL_SANDBOX_DIR
from sculptor.utils.file_utils import copy_dir


def get_local_environment_sandbox_directory(environment_prefix: str) -> Path:
    # Create a separate "namespace" for each environment service.
    return LOCAL_SANDBOX_DIR / environment_prefix


def build_local_environment(
    local_image: LocalImage,
    config: LocalEnvironmentConfig,
    environment_prefix: str = "",
    provider_health_check: Callable[[], ProviderStatus] | None = None,
) -> LocalEnvironment:
    source_path = local_image.image_path
    if not source_path:
        raise ValueError("No source path provided for local image record.")

    sandbox_path = _create_sandbox_path(uuid4().hex, environment_prefix)
    environment = LocalEnvironment(
        environment_id=LocalEnvironmentID(str(sandbox_path)),
        config=config,
        _provider_health_check=provider_health_check,
        project_id=local_image.project_id,
    )
    _copy_code_to_user_project_path(source_path, environment)
    environment.to_host_path(environment.get_state_path()).mkdir(parents=True, exist_ok=True)
    environment.to_host_path(environment.get_artifacts_path()).mkdir(parents=True, exist_ok=True)
    return environment


def _create_sandbox_path(sandbox_path_id: str, environment_prefix: str = "") -> Path:
    if not environment_prefix:
        sandbox_path = LOCAL_SANDBOX_DIR / sandbox_path_id
    else:
        sandbox_path = get_local_environment_sandbox_directory(environment_prefix) / sandbox_path_id
    sandbox_path.mkdir(parents=True, exist_ok=True)
    return sandbox_path


def _copy_code_to_user_project_path(source_path: Path, environment: LocalEnvironment) -> None:
    assert source_path.exists(), f"Source path {source_path} does not exist"
    destination_path = environment.to_host_path(environment.get_workspace_path())
    logger.info("Copying {} to {}", source_path, destination_path)
    if source_path.is_dir():
        copy_dir(source_path, destination_path, dirs_exist_ok=True)
    else:
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination_path)


def destroy_outdated_local_environments(environment_prefix: str) -> None:
    _handle_outdated_local_environments(environment_prefix=environment_prefix, is_stopped=False)


def stop_outdated_local_environments(environment_prefix: str) -> None:
    _handle_outdated_local_environments(environment_prefix=environment_prefix, is_stopped=True)


def _handle_outdated_local_environments(environment_prefix: str, is_stopped: bool) -> None:
    base_dir = get_local_environment_sandbox_directory(environment_prefix)
    if not base_dir.exists():
        return
    for folder in base_dir.iterdir():
        if folder.is_dir():
            if is_stopped:
                stop_local_environment(folder)
            else:
                remove_local_environment(folder)
