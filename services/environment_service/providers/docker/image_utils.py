import json
import os
import platform
import re
import shlex
import tempfile
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Final
from urllib.request import urlretrieve

from loguru import logger

from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.agents.data_types.ids import TaskID
from imbue_core.async_monkey_patches import log_exception
from imbue_core.common import generate_id
from imbue_core.constants import ExceptionPriority
from imbue_core.processes.local_process import run_blocking
from imbue_core.processes.local_process import run_streaming
from imbue_core.subprocess_utils import ProcessError
from sculptor import version
from sculptor.cli.ssh_utils import ensure_local_sculptor_ssh_configured
from sculptor.database.models import TaskID
from sculptor.interfaces.environments.v1.base import LocalDockerImage
from sculptor.interfaces.environments.v1.errors import ImageConfigError
from sculptor.interfaces.environments.v1.errors import ProviderError
from sculptor.primitives.constants import USER_FACING_LOG_TYPE
from sculptor.primitives.ids import DockerContainerID
from sculptor.primitives.ids import DockerImageID
from sculptor.services.environment_service.api import TaskImageCleanupData
from sculptor.utils.timeout import log_runtime
from sculptor.utils.timeout import log_runtime_decorator

_CDN_PREFIX: Final[str] = "https://d2rpy6crlmjake.cloudfront.net/images/"

# Global dictionary to store locks by image URL
_image_url_locks: dict[str, threading.Lock] = {}
_image_url_locks_lock = threading.Lock()


def _get_or_create_image_url_lock(image_url: str) -> threading.Lock:
    """Get or create a lock for the given image URL."""
    with _image_url_locks_lock:
        if image_url not in _image_url_locks:
            _image_url_locks[image_url] = threading.Lock()
        return _image_url_locks[image_url]


def _fetch_from_cdn_and_docker_load(image_url: str) -> None:
    """
    Fetch a Docker image from CDN and load it into Docker.

    This helper function downloads the image from CloudFront CDN and loads it
    into the local Docker daemon. Any exceptions are propagated to the caller.

    Args:
        image_url: Docker image URL (e.g., "ghcr.io/imbue-ai/sculptor:tag@sha256:...")

    Raises:
        Exception: Any exception that occurs during download or Docker load
    """
    # Generate safe name for CDN path
    platform_name = get_platform_architecture()
    safe_name = docker_image_url_to_s3_safe_name(image_url, platform_name)
    cdn_url = f"{_CDN_PREFIX}{safe_name}.tar"

    # Download section
    # TODO: It would be nice to get started on this fetch before we even know that Docker exists and is running!
    # It adds complexity to the "state" things, though.
    with tempfile.NamedTemporaryFile(suffix=".tar", delete=True) as temp_file:
        # TODO: It could be nice to have this file already downloaded before we we even know we can load it into Docker.
        temp_path = temp_file.name
        with log_runtime(f"DownloadFromCDN:{safe_name}"):
            logger.info(f"Downloading image from {cdn_url}")
            timeout_tracker = _UrlRetrieveTimeoutTracker()
            urlretrieve(cdn_url, temp_path, reporthook=timeout_tracker.report_hook)
            logger.info("Downloaded image from CDN successfully")

        # Loading section
        with log_runtime(f"DockerLoad:{image_url}"):
            logger.info(f"Loading image from {temp_path}")
            load_result = run_streaming(
                command=["docker", "load", "-i", temp_path],
                is_checked=True,
                on_output=lambda line, is_stderr: logger.debug(line.strip()),
                timeout=180.0,
            )
            logger.info("Loaded image from {}, load result: {}", temp_path, load_result)


@log_runtime_decorator()
def build_docker_image(
    dockerfile_path: Path,
    project_id: ProjectID,
    cached_repo_tarball_parent_directory: Path | None = None,
    tag: str | None = None,
    disable_cache: bool = False,
    secrets: dict[str, str] | None = None,
    build_path: Path | None = None,
    base_image_tag: str | None = None,
) -> LocalDockerImage:
    """Build a Docker image from a Dockerfile.

    build_path is a synonym for Docker's build context, which is an unnamed argument to docker build.
    """
    if not dockerfile_path.exists():
        raise FileNotFoundError(f"Dockerfile not found at {dockerfile_path}")

    if secrets is None:
        secrets = {}

    # Generate a unique tag if not provided
    if tag is None:
        tag = f"sculptor-image:{generate_id()[:8]}"

    # Build the Docker image
    build_command = [
        *("docker", "buildx", "build"),
        "--progress=plain",
        "--output=type=docker,compression=uncompressed",
        *("-f", str(dockerfile_path)),
        *("-t", tag),
        *("--build-arg", f"BUILT_FROM_SCULPTOR_VERSION={version.__version__}"),
        *("--build-arg", f"BUILT_FROM_SCULPTOR_GIT_HASH={version.__git_sha__}"),
        # TODO: Get rid of these when we can.
        *("--build-arg", f"USER_UID={os.getuid()}"),
        *("--build-arg", f"GROUP_GID={os.getgid()}"),
    ]
    if cached_repo_tarball_parent_directory:
        build_command.extend(("--build-context", f"imbue_user_repo={cached_repo_tarball_parent_directory}"))

    ssh_keypair_dir = ensure_local_sculptor_ssh_configured()
    build_command.extend(("--build-context", f"ssh_keypair_dir={ssh_keypair_dir}"))

    if base_image_tag:
        build_command.extend(("--build-arg", f"BASE_IMAGE={base_image_tag}"))

    if disable_cache:
        build_command.append("--no-cache")

    build_path = build_path or dockerfile_path.parent
    build_command.append(str(build_path))

    logger.info("Building Docker image with tag {}", tag)

    build_command_string = " ".join(shlex.quote(arg) for arg in build_command)
    logger.debug("Building Docker image with build_path={}:\n{}", build_path, build_command_string)

    try:
        run_streaming(
            command=build_command,
            on_output=lambda line, is_stderr: logger.debug(line.strip()),
            cwd=build_path,
            trace_log_context={"sandbox_path": str(build_path), "log_type": USER_FACING_LOG_TYPE},
            env={**os.environ, **secrets},
        )
    except ProcessError as e:
        error_msg = f"Docker build failed - is your Docker up-to-date? Exit code {e.returncode}: {build_command_string}\nstdout=\n{e.stdout}\nstderr=\n{e.stderr}"
        if "ERROR: failed to solve" in e.stderr:
            # NOTE: this might not be the best way to distinguish between image config errors and other errors
            # but it's the best we can do for now
            raise ImageConfigError(error_msg) from e
        raise ProviderError(error_msg) from e

    # Get the image ID
    inspect_result = run_blocking(
        command=["docker", "inspect", "-f", "{{.Id}}", tag],
        is_checked=False,
    )

    if inspect_result.returncode != 0:
        raise ProviderError(f"Failed to inspect built image: {inspect_result.stderr}")

    docker_image_id = inspect_result.stdout.strip()

    # Save to database
    full_id = DockerImageID(docker_image_id)

    logger.info("Built Docker image {} with tag {}", full_id, tag)
    return LocalDockerImage(image_id=full_id, docker_image_tag=tag, project_id=project_id)


def delete_docker_image_and_any_stopped_containers(image_id: str) -> tuple[bool, list[DockerContainerID]]:
    """Delete a Docker image by image ID."""
    deleted_container_ids = []
    # first delete all *stopped* docker containers that were created from this image
    try:
        container_ids = (
            run_blocking(
                command=["docker", "ps", "-a", "-q", "-f", "status=exited", "-f", f"ancestor={image_id}"],
                is_output_traced=False,
            )
            .stdout.strip()
            .splitlines(keepends=False)
        )
    # TODO: probably need some better error handling here
    except ProcessError as e:
        log_exception(e, f"Failed to list containers for {image_id}", priority=ExceptionPriority.LOW_PRIORITY)
        return False, deleted_container_ids

    for container_id in container_ids:
        try:
            run_blocking(
                command=["docker", "rm", container_id],
                is_output_traced=False,
            )
            deleted_container_ids.append(DockerContainerID(container_id))
            logger.debug("Successfully deleted stopped container {} for image {}", container_id, image_id)
        except ProcessError as e:
            log_exception(
                e, f"Failed to delete stopped containers for image {image_id}", priority=ExceptionPriority.LOW_PRIORITY
            )
            return False, deleted_container_ids

    try:
        # The only time we want to delete an image is when it is genuinely unused; i.e.
        # not being used by a current running container. The docker rmi command fails when
        # it is asked to delete an image used by a currently running container, while allowing
        # you to delete outdated snapshots for currently running containers.

        run_blocking(
            command=["docker", "rmi", image_id],
            is_output_traced=False,
        )
        logger.debug("Successfully deleted Docker image: {}", image_id)
        return True, deleted_container_ids
    except ProcessError as e:
        image_still_exists_against_our_wishes = run_blocking(
            command=["docker", "inspect", image_id],
            is_checked=False,
            is_output_traced=False,
        )
        if image_still_exists_against_our_wishes.returncode != 0:
            return True, deleted_container_ids
        else:
            if "image is being used by running container" in e.stderr:
                pass
            else:
                log_exception(e, f"Failed to delete Docker image {image_id}")
            return False, deleted_container_ids
    except Exception as e:
        log_exception(e, f"Error deleting Docker image {image_id}")
        return False, deleted_container_ids


def _get_image_ids_with_running_containers() -> tuple[str, ...]:
    try:
        container_ids_result = run_blocking(command=["docker", "ps", "-q"])
        container_ids = container_ids_result.stdout.strip().splitlines()
        if len(container_ids) == 0:
            return ()
        image_ids_result = run_blocking(
            command=[
                "docker",
                "inspect",
                "--format={{.Image}}",
                *container_ids,
            ]
        )
    except ProcessError as e:
        log_exception(e, "Error getting image IDs with running containers", priority=ExceptionPriority.LOW_PRIORITY)
        return ()

    active_image_ids: set[str] = set()
    for line in image_ids_result.stdout.strip().splitlines():
        if line.strip():
            active_image_ids.add(line.strip())

    return tuple(active_image_ids)


class DeletionTier(Enum):
    # if an image is being used in multiple tasks, we take the lowest tier of the tasks

    # never delete: images on running containers or the latest image of a task
    NEVER_DELETE = 0
    # rarely delete: historical images on active tasks that are not being used by a running container
    RARELY_DELETE = 1
    # sometimes delete: historical images on archived tasks that are not being used by a running container
    SOMETIMES_DELETE = 2
    # always delete: images for deleted tasks
    ALWAYS_DELETE = 3


def _classify_image_tier(image_id: str, associated_task_metadata: TaskImageCleanupData) -> DeletionTier:
    if associated_task_metadata.is_deleted:
        return DeletionTier.ALWAYS_DELETE
    if image_id == associated_task_metadata.last_image_id:
        return DeletionTier.NEVER_DELETE
    if associated_task_metadata.is_archived:
        return DeletionTier.SOMETIMES_DELETE
    return DeletionTier.RARELY_DELETE


def _get_task_ids_by_image_id(task_metadata_by_task_id: dict[TaskID, TaskImageCleanupData]) -> dict[str, list[TaskID]]:
    task_ids_by_image_id: dict[str, list[TaskID]] = dict()
    for task_id, task_metadata in task_metadata_by_task_id.items():
        for image_id in task_metadata.all_image_ids:
            task_ids_by_image_id.setdefault(image_id, []).append(task_id)
    return task_ids_by_image_id


def _get_tier_by_image_id(
    task_metadata_by_task_id: dict[str, TaskImageCleanupData],
    active_image_ids: tuple[str, ...],
) -> dict[str, DeletionTier]:
    tier_by_image_id: dict[str, DeletionTier] = dict()
    task_ids_by_image_id = _get_task_ids_by_image_id(task_metadata_by_task_id)

    for image_id, task_ids in task_ids_by_image_id.items():
        if image_id in active_image_ids:
            logger.debug("Image {} is in active image IDs - never delete", image_id)
            tier_by_image_id[image_id] = DeletionTier.NEVER_DELETE
        else:
            tiers = []
            for task_id in task_ids:
                task_metadata = task_metadata_by_task_id[task_id]
                tiers.append(_classify_image_tier(image_id=image_id, associated_task_metadata=task_metadata))
            if any(tier == DeletionTier.NEVER_DELETE for tier in tiers):
                tier_by_image_id[image_id] = DeletionTier.NEVER_DELETE
            elif any(tier == DeletionTier.RARELY_DELETE for tier in tiers):
                tier_by_image_id[image_id] = DeletionTier.RARELY_DELETE
            elif any(tier == DeletionTier.SOMETIMES_DELETE for tier in tiers):
                tier_by_image_id[image_id] = DeletionTier.SOMETIMES_DELETE
            else:
                tier_by_image_id[image_id] = DeletionTier.ALWAYS_DELETE
            logger.debug("Image {} has been assigned tier {}", image_id, tier_by_image_id[image_id])
    return tier_by_image_id


def _get_current_image_ids() -> tuple[str, ...]:
    result = run_blocking(command=["docker", "images", "--no-trunc", "--format", "json"])
    image_ids = set()
    for line in result.stdout.strip().splitlines():
        if line.strip():
            full_image_id = json.loads(line)["ID"]
            image_ids.add(full_image_id.split(":")[1].strip())
            logger.trace(line)
    return tuple(image_ids)


def get_image_ids_to_delete(
    task_metadata_by_task_id: dict[str, TaskImageCleanupData],
    minimum_deletion_tier: DeletionTier,
) -> tuple[str, ...]:
    logger.debug("task_metadata_by_task_id: {}", task_metadata_by_task_id)
    existing_image_ids = _get_current_image_ids()
    active_image_ids = _get_image_ids_with_running_containers()
    logger.debug("active_image_ids: {}", active_image_ids)
    return _calculate_image_ids_to_delete(
        task_metadata_by_task_id, active_image_ids, existing_image_ids, minimum_deletion_tier
    )


def _calculate_image_ids_to_delete(
    task_metadata_by_task_id: dict[str, TaskImageCleanupData],
    active_image_ids: tuple[str, ...],
    existing_image_ids: tuple[str, ...],
    minimum_deletion_tier: DeletionTier,
) -> tuple[str, ...]:
    tier_by_image_id = _get_tier_by_image_id(task_metadata_by_task_id, active_image_ids)
    image_ids = set()
    for image_id, tier in tier_by_image_id.items():
        if tier.value > minimum_deletion_tier.value and image_id in existing_image_ids:
            # only attempt to delete images that are above the minimum deletion tier and still exist in the system
            logger.debug("Adding image {} to deletion list", image_id)
            image_ids.add(image_id)
    return tuple(image_ids)


def docker_image_url_to_s3_safe_name(image_url: str, target_platform: str) -> str:
    """
    Convert a Docker image URL and platform to an S3-safe path component.

    Replaces unsafe characters in the image URL and platform to make them S3-compatible.

    Args:
        image_url: Docker image URL (e.g., "ubuntu:20.04", "gcr.io/project/image:v1.0")
        platform: Platform architecture (e.g., "amd64", "arm64")

    Returns:
        S3-safe string combining image URL and platform

    Examples:
        >>> docker_image_url_to_s3_safe_name("ubuntu:20.04", "amd64")
        'ubuntu-20.04_amd64'

        >>> docker_image_url_to_s3_safe_name("gcr.io/my-project/my-image:v1.2.3", "arm64")
        'gcr.io/my-project/my-image-v1.2.3_arm64'

        >>> docker_image_url_to_s3_safe_name("nginx@sha256:abc123def456", "amd64")
        'nginx-sha256-abc123def456_amd64'
    """
    # Replace unsafe characters with safe ones
    # S3 keys can contain: letters, numbers, hyphens, underscores, periods
    # Replace problematic characters: / : @ . with safe alternatives
    result = f"{image_url}_{target_platform}"
    result = re.sub(r"[^-_/.a-zA-Z0-9]", "-", result)
    return result


def get_platform_architecture() -> str:
    """
    Determine the platform architecture for Docker images.

    Returns:
        Platform name ("amd64" or "arm64")

    Examples:
        >>> get_platform_architecture() in ["amd64", "arm64"]
        True
    """
    arch = platform.machine().lower()
    if arch == "x86_64":
        return "amd64"
    elif arch == "aarch64" or arch == "arm64":
        return "arm64"
    else:
        logger.info(f"Unknown architecture {arch}, defaulting to amd64")
        return "amd64"


def fetch_image_from_cdn(image_url: str) -> None:
    """
    Fetch a Docker image from CDN if it's not already available locally.

    First checks if the image exists locally using `docker inspect`. If not,
    tries to download and load from CloudFront CDN. If CDN fetch fails, falls back
    to direct Docker pull.

    This method is locked per image URL to prevent concurrent downloads of the same image.

    Args:
        image_url: Docker image URL (e.g., "ghcr.io/imbue-ai/sculptor:tag@sha256:...")
    """
    image_lock = _get_or_create_image_url_lock(image_url)

    with image_lock:
        with log_runtime(f"FetchImageFromCDN:{image_url}"):
            logger.info("Checking if image {} is available locally", image_url)

            # Check if image exists locally
            inspect_result = run_blocking(
                command=["docker", "inspect", image_url],
                is_checked=False,
                is_output_traced=False,
            )
            if inspect_result.returncode == 0:
                logger.trace("Image {} already available locally", image_url)
                return

            logger.info("Image {} not found locally, fetching from CDN.", image_url)

            # Try to fetch from CDN and load into Docker
            try:
                _fetch_from_cdn_and_docker_load(image_url)
                logger.info("Successfully fetched image from CDN, {}", image_url)
            except Exception as e:
                log_exception(e, f"Failed to fetch image {image_url} from CDN, will fallback to docker pull")

            # We Have to do this `docker pull``, even if the docker load above succeeded.
            # It has the effect of registering "image_url" with docker, and that's what we check for
            # above to decide if we need to re-run this method or if docker already knows about "image_url".
            # If we didn't `docker pull` here, the next call to this method would do the fetch again.
            # This should not actually fetch many bytes, but does talk to the registry.
            with log_runtime(f"DockerPull:{image_url}"):
                run_streaming(
                    command=["docker", "pull", image_url],
                    is_checked=True,
                    on_output=lambda line, is_stderr: logger.debug(line.strip()),
                )

        logger.success("Successfully loaded image {}.", image_url)


class _UrlRetrieveTimeoutTracker:
    def __init__(self, timeout_seconds: float = 180.0) -> None:
        self.timeout_seconds = timeout_seconds
        self.start_time = time.time()

    def report_hook(self, block_num: int, block_size: int, total_size: int) -> None:
        elapsed_time = time.time() - self.start_time
        if elapsed_time > self.timeout_seconds:
            downloaded_bytes = block_num * block_size
            raise TimeoutError(
                f"Download timed out after {elapsed_time:.1f} seconds. {downloaded_bytes=}, {total_size=}."
            )
