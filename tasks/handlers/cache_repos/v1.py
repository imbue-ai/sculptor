import os
from pathlib import Path
from urllib.parse import urlparse

from loguru import logger

from imbue_core.gitlab_management import GITLAB_TOKEN_NAME
from sculptor.interfaces.environments.v1.base import LocalDevcontainerImageConfig
from sculptor.primitives.ids import RequestID
from sculptor.services.environment_service.providers.docker.devcontainer_image_builder import (
    get_devcontainer_json_path_from_repo_or_default,
)
from sculptor.services.task_service.data_types import ServiceCollectionForTask

IMBUE_TESTING_GITLAB_MIRROR_REPO_URL = (
    "https://gitlab.com/generally-intelligent/gitlab-management-test-repos/integration_testing.git"
)


def cache_repos_task_v1(services: ServiceCollectionForTask) -> None:
    settings = services.settings
    if settings.GITLAB_DEFAULT_TOKEN != "":
        os.environ[GITLAB_TOKEN_NAME] = settings.GITLAB_DEFAULT_TOKEN
        os.environ["GITLAB_PROJECT_URL"] = IMBUE_TESTING_GITLAB_MIRROR_REPO_URL
        os.environ["GITLAB_URL"] = "https://gitlab.com"

    with services.data_model_service.open_transaction(RequestID()) as transaction:
        all_projects = transaction.get_projects()
        for project in all_projects:
            logger.info("Caching repo for project {}", project.name)
            if not project.user_git_repo_url:
                continue

            active_repo_path = Path(urlparse(project.user_git_repo_url).path)
            cached_repo_path = project.get_cached_repo_path()

            devcontainer_json_path = get_devcontainer_json_path_from_repo_or_default(active_repo_path)
            image_config = LocalDevcontainerImageConfig(
                devcontainer_json_path=str(devcontainer_json_path),
            )
            logger.info("Creating image for image_config={}", image_config)

            # MILLAN TODO: add back once per day caching
            services.environment_service.ensure_image(
                image_config,
                secrets={},
                active_repo_path=active_repo_path,
                cached_repo_path=cached_repo_path,
                project_id=project.object_id,
            )
            logger.info("Finished creating image for image_config={}", image_config)
