import hashlib
from pathlib import Path
from tempfile import gettempdir

from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.common import generate_id
from imbue_core.processes.local_process import run_blocking
from imbue_core.testing_utils import temp_dir
from sculptor.interfaces.environments.v1.base import LocalDevcontainerImageConfig
from sculptor.services.environment_service.default_implementation import create_archived_repo
from sculptor.services.environment_service.providers.docker.devcontainer_image_builder import (
    build_local_devcontainer_image,
)
from sculptor.services.environment_service.providers.docker.devcontainer_image_builder import (
    get_devcontainer_json_path_from_repo_or_default,
)
from sculptor.testing.server_utils import TEST_ENVIRONMENT_PREFIX


def make_default_images():
    baseline_repo_path = Path("/tmp/baseline_repo_path/")
    baseline_repo_path.mkdir(parents=True, exist_ok=True)
    run_blocking(["git", "init"], cwd=baseline_repo_path)
    # There won't be a devcontainer.json in the baseline repo path, so we'll end up with the default one.
    devcontainer_json_path = get_devcontainer_json_path_from_repo_or_default(Path("/tmp/baseline_repo_path"))
    image_config = LocalDevcontainerImageConfig(
        devcontainer_json_path=str(devcontainer_json_path),
    )
    environment_prefix = f"{TEST_ENVIRONMENT_PREFIX}-{generate_id()}"
    image_name = f"{environment_prefix}{hashlib.sha256(str(baseline_repo_path).encode()).hexdigest()}"
    image_name_with_explicit_tag = f"{image_name}:{generate_id()}"
    with temp_dir(gettempdir()) as place_to_put_archived_mock_repo:
        create_archived_repo(baseline_repo_path, place_to_put_archived_mock_repo / "repo.tar")
        image = build_local_devcontainer_image(
            image_config,
            project_id=ProjectID(),
            tag=image_name_with_explicit_tag,
            cached_repo_tarball_parent_directory=place_to_put_archived_mock_repo,
        )
        print(f"Built image: {image}")
