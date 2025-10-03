import json
from enum import StrEnum
from pathlib import Path
from typing import Final

from loguru import logger

from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.async_monkey_patches import log_exception
from imbue_core.background_setup import BackgroundSetup
from imbue_core.sculptor.telemetry import PosthogEventModel
from imbue_core.sculptor.telemetry import PosthogEventPayload
from imbue_core.sculptor.telemetry import emit_posthog_event
from imbue_core.sculptor.telemetry import with_consent
from imbue_core.sculptor.telemetry_constants import ConsentLevel
from imbue_core.sculptor.telemetry_constants import ProductComponent
from imbue_core.sculptor.telemetry_constants import SculptorPosthogEvent
from imbue_core.thread_utils import ObservableThread
from sculptor.interfaces.environments.v1.base import LocalDevcontainerImageConfig
from sculptor.interfaces.environments.v1.base import LocalDockerImage
from sculptor.services.environment_service.providers.docker.image_utils import build_docker_image
from sculptor.services.environment_service.providers.docker.image_utils import fetch_image_from_cdn
from sculptor.services.environment_service.providers.docker.volume_mounted_nix_control_plane import (
    CONTROL_PLANE_FETCH_BACKGROUND_SETUP,
)
from sculptor.utils.timeout import log_runtime_decorator

_IMBUE_ADDONS_DOCKERFILE_PATH: Final[Path] = Path(__file__).parent / "imbue_addons" / "Dockerfile.imbue_addons"


class DevcontainerBuildPath(StrEnum):
    """Control flow paths for devcontainer image building."""

    DOCKERFILE_NAME = "dockerfile_name"
    IMAGE_NAME = "image_name"
    FALLBACK_TO_DEFAULT = "fallback_to_default"


class DevcontainerBuildEventData(PosthogEventPayload):
    """PostHog event data for devcontainer build operations."""

    control_flow_path: str = with_consent(ConsentLevel.PRODUCT_ANALYTICS)
    devcontainer_json_path: str = with_consent(ConsentLevel.PRODUCT_ANALYTICS)
    tag: str = with_consent(ConsentLevel.PRODUCT_ANALYTICS)
    fallback_reason: str | None = with_consent(ConsentLevel.PRODUCT_ANALYTICS)


class DevcontainerError(ValueError):
    """Error raised when there's an issue with the DevcontainerError."""

    pass


def get_default_devcontainer_json_path() -> Path:
    result = Path(__file__).parent / "default_devcontainer" / "devcontainer.json"
    assert result.exists(), f"Default devcontainer.json not found at {result}"
    return result


def get_default_devcontainer_image_reference() -> str:
    """Parse and return the image reference from the default devcontainer.json."""
    default_devcontainer_path = get_default_devcontainer_json_path()
    json_contents = json.loads(default_devcontainer_path.read_text("utf-8"))
    image_reference = json_contents.get("image")
    assert image_reference, f"No 'image' field found in default devcontainer.json at {default_devcontainer_path}"
    return image_reference


@log_runtime_decorator()
def _docker_pull_default_devcontainer() -> None:
    """Private function to run docker pull in background."""
    image_reference = get_default_devcontainer_image_reference()
    # Try to fetch the devcontainer image from CDN first
    logger.info("Starting background docker pull for: {}", image_reference)
    fetch_image_from_cdn(image_reference)


PULL_DEFAULT_DEVCONTAINER_BACKGROUND_SETUP: Final[BackgroundSetup] = BackgroundSetup(
    "DockerPullDefaultDevcontainerBackgroundSetup",
    _docker_pull_default_devcontainer,
)


def start_control_plane_background_setup(thread_suffix: str) -> list[ObservableThread]:
    """Starting control plane background setup tasks.  Does not block, just starts background threads."""
    logger.info("Starting background setup tasks for devcontainers.")
    return [
        PULL_DEFAULT_DEVCONTAINER_BACKGROUND_SETUP.start_run_in_background(
            thread_name=f"DockerPullDefaultDevcontainerBackgroundSetup_{thread_suffix}"
        ),
        CONTROL_PLANE_FETCH_BACKGROUND_SETUP.start_run_in_background(
            thread_name=f"ControlPlaneFetchBackgroundSetup_{thread_suffix}"
        ),
    ]


def get_devcontainer_json_path_from_repo_or_default(repo_path: Path) -> Path:
    """Find the user's devcontainer.json file, or use our default one so they don't have to specify it."""
    paths = [
        ".devcontainer/devcontainer.json",
        "devcontainer.json",
    ]
    for p in paths:
        if (repo_path / p).exists():
            logger.info("Found devcontainer.json at {}", p)
            return repo_path / p
    result = get_default_devcontainer_json_path()
    logger.info("No devcontainer.json found, using the Sculptor default at {}", result)
    return result


@log_runtime_decorator()
def build_local_devcontainer_image(
    config: LocalDevcontainerImageConfig,
    cached_repo_tarball_parent_directory: Path,
    project_id: ProjectID,
    tag: str,
    secrets: dict[str, str] | None = None,
) -> LocalDockerImage:
    """Build a Docker image from a devcontainer.json configuration."""
    logger.info("Building local devcontainer image from {} with tag {}", config.devcontainer_json_path, tag)

    # Start control plane volume setup in background thread
    control_plane_thread = CONTROL_PLANE_FETCH_BACKGROUND_SETUP.start_run_in_background(
        thread_name="ControlPlaneFetchJoinedThread"
    )

    devcontainer_path = Path(config.devcontainer_json_path)
    if not devcontainer_path.exists():
        raise FileNotFoundError(f"devcontainer.json not found at {devcontainer_path}")

    try:
        json_contents = json.loads(devcontainer_path.read_text("utf-8"))
        # TODO: Consider somehow invoking the reference implementation via:
        # devcontainer build --workspace-folder devcontainer_path.parent.
        # For now, we are just supporting a very limited amount of the devcontainer.json format.

        # We support two different ways to build a devcontainer image:
        # 1. From a Dockerfile: devcontainer.json's build.dockerfile field
        # 2. From an image: devcontainer.json's image field
        # Exactly one of these must be specified, and we check this.
        dockerfile_name = json_contents.get("build", {}).get("dockerfile")
        image_name = json_contents.get("image")
        if not dockerfile_name and not image_name:
            raise DevcontainerError(
                f"devcontainer.json must contain a 'build.dockerfile' field or an 'image' field, {json_contents=}"
            )
        elif dockerfile_name and image_name:
            raise DevcontainerError(
                f"devcontainer.json cannot contain both a 'build.dockerfile' field and an 'image' field, {json_contents=}"
            )
        # Initialize PostHog event data - control_flow_path and fallback_reason will be set in the branches
        control_flow_path: DevcontainerBuildPath
        fallback_reason: str | None = None

        if dockerfile_name:
            build_context = json_contents.get("build", {}).get("context", ".")
            build_context_path = devcontainer_path.parent / build_context
            # Build from a Dockerfile
            dockerfile_path = devcontainer_path.parent / dockerfile_name
            if not dockerfile_path.exists():
                raise DevcontainerError(f"Dockerfile not found at {dockerfile_path}")

            user_image_tag = f"{tag}_user_image_to_wrap"

            logger.info(
                "Building user image from Dockerfile at {}, with build context at {}",
                dockerfile_path,
                build_context_path,
            )
            user_image: LocalDockerImage = build_docker_image(
                dockerfile_path,
                project_id=project_id,
                tag=user_image_tag,
                build_path=build_context_path,
                secrets=secrets,
            )
            logger.info("Built user image tag with tag={}, id={}", user_image_tag, user_image.image_id)
            control_flow_path = DevcontainerBuildPath.DOCKERFILE_NAME
        else:
            # Use the pre-existing image.
            # The great thing about this path is that it skips an entire docker build step.
            assert image_name is not None
            user_image_tag = image_name
            control_flow_path = DevcontainerBuildPath.IMAGE_NAME
    except Exception as e:
        # TODO: Somehow get a message into Sculptor's message queue with the logs from the failure.
        log_exception(e, "Failed to build user Dockerfile, falling back to default devcontainer image")
        fallback_reason = f"Dockerfile build failed: {type(e).__name__}"

        # Fall back to using the default devcontainer image
        user_image_tag = get_default_devcontainer_image_reference()
        control_flow_path = DevcontainerBuildPath.FALLBACK_TO_DEFAULT

    logger.info("Building Imbue's wrapper image around user_image_tag={}", user_image_tag)
    try:
        wrapped_image: LocalDockerImage = build_docker_image(
            _IMBUE_ADDONS_DOCKERFILE_PATH,
            project_id=project_id,
            cached_repo_tarball_parent_directory=cached_repo_tarball_parent_directory,
            tag=tag,
            secrets=secrets,
            base_image_tag=user_image_tag,
        )
        logger.info("Built Imbue's wrapper image with tag={}", tag)
    except Exception as e:
        logger.info(
            "Failed to build Imbue's wrapper around user_image_tag={}, falling back to default devcontainer image: {}",
            user_image_tag,
            e,
        )
        # The reason this is almost repeated is to handle the case where devcontainer.json specifies an image,
        # but the image is not valid.  In that case, there's no build step, for the user image, but the
        # build_docker_image above for _IMBUE_ADDONS_DOCKERFILE_PATH will fail, and we fall back to using
        # the default devcontainer image.
        wrapped_image: LocalDockerImage = build_docker_image(
            _IMBUE_ADDONS_DOCKERFILE_PATH,
            project_id=project_id,
            cached_repo_tarball_parent_directory=cached_repo_tarball_parent_directory,
            tag=tag,
            secrets=secrets,
            base_image_tag=get_default_devcontainer_image_reference(),
        )
        logger.info("As a fallback, built Imbue's wrapper image with tag={}", tag)
        control_flow_path = DevcontainerBuildPath.FALLBACK_TO_DEFAULT

    # Emit PostHog telemetry event
    try:
        event_data = DevcontainerBuildEventData(
            control_flow_path=control_flow_path,
            devcontainer_json_path=str(devcontainer_path),
            tag=tag,
            fallback_reason=fallback_reason,
        )
        posthog_event = PosthogEventModel[
            DevcontainerBuildEventData
        ](
            name=SculptorPosthogEvent.TASK_START_MESSAGE,  # Using existing event - could add DEVCONTAINER_BUILD if needed
            component=ProductComponent.TASK,
            payload=event_data,
        )
        emit_posthog_event(posthog_event)
    except Exception as e:
        logger.info("Failed to emit devcontainer build telemetry: {}", e)

    # Wait for control plane thread to complete and raise any errors
    control_plane_thread.join()  # This will raise any exception from the background thread

    return wrapped_image
