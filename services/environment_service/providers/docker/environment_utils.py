import os
import tempfile
import time
import uuid
from concurrent.futures import Future
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from loguru import logger

from imbue_core.async_monkey_patches import log_exception
from imbue_core.common import generate_id
from imbue_core.constants import ExceptionPriority
from imbue_core.itertools import flatten
from imbue_core.processes.local_process import run_blocking
from imbue_core.subprocess_utils import ProcessError
from imbue_core.subprocess_utils import ProcessSetupError
from sculptor.constants import ROOT_PATH
from sculptor.interfaces.environments.v1.base import LocalDockerEnvironmentConfig
from sculptor.interfaces.environments.v1.base import LocalDockerImage
from sculptor.interfaces.environments.v1.constants import AGENT_DATA_PATH
from sculptor.interfaces.environments.v1.constants import SCULPTOR_USER
from sculptor.interfaces.environments.v1.errors import EnvironmentNotFoundError
from sculptor.interfaces.environments.v1.errors import ImageConfigError
from sculptor.interfaces.environments.v1.errors import ProviderError
from sculptor.interfaces.environments.v1.errors import SetupError
from sculptor.interfaces.environments.v1.provider_status import ProviderStatus
from sculptor.primitives.constants import USER_FACING_LOG_TYPE
from sculptor.primitives.ids import DockerContainerID
from sculptor.services.environment_service.environments.docker_environment import DockerEnvironment
from sculptor.services.environment_service.environments.docker_environment import remove_docker_container
from sculptor.services.environment_service.environments.docker_environment import stop_docker_container
from sculptor.services.environment_service.providers.docker.errors import DockerError
from sculptor.services.environment_service.providers.docker.errors import DockerNotInstalledError
from sculptor.services.environment_service.providers.docker.errors import NoServerPortBoundError
from sculptor.services.environment_service.providers.docker.errors import ProviderIsDownError
from sculptor.services.environment_service.providers.docker.volume_mounted_nix_control_plane import (
    CONTROL_PLANE_FETCH_BACKGROUND_SETUP,
)
from sculptor.services.environment_service.providers.docker.volume_mounted_nix_control_plane import (
    CONTROL_PLANE_VOLUME_DOCKER_ARGS,
)
from sculptor.utils.build import get_sculptor_folder
from sculptor.utils.timeout import log_runtime_decorator


@log_runtime_decorator()
def build_docker_environment(
    docker_image: LocalDockerImage,
    config: LocalDockerEnvironmentConfig,
    name: str | None = None,
    environment_prefix: str = "",
    provider_health_check: Callable[[], ProviderStatus] | None = None,
) -> tuple[DockerEnvironment, list[str]]:
    """Create a Docker container from an image."""

    # This needs to happen whether we are building a new image or starting an existing one.
    CONTROL_PLANE_FETCH_BACKGROUND_SETUP.ensure_finished()

    # Generate container name if not provided
    if name is None:
        name = generate_id()
    name = environment_prefix + name

    create_command, group_id, user_id = get_base_docker_create_args(name, config.server_port_by_name)

    container_id = create_docker_container(create_command + [docker_image.docker_image_tag], docker_image, name)

    # Now retrieve the port that each server is mapped to
    external_port_by_name = get_external_port_by_name_mapping(container_id, config.server_port_by_name)

    environment = DockerEnvironment(
        config=config,
        environment_id=DockerContainerID(container_id),
        server_port_by_name=external_port_by_name,
        _provider_health_check=provider_health_check,
        environment_prefix=environment_prefix,
        project_id=docker_image.project_id,
    )

    setup_docker_environment(environment, group_id, user_id)
    return environment, create_command


def setup_docker_environment(environment: DockerEnvironment, group_id: int, user_id: int) -> None:
    with logger.contextualize(log_type=USER_FACING_LOG_TYPE):
        logger.info("Created Docker sandbox {container_id}", container_id=environment.container_id)
        docker_on_create_command = [
            *("docker", "exec"),
            *("--user", "root"),
            environment.container_id,
            *(
                "bash",
                "-c",
                f"/imbue_addons/imbue_post_container_build.sh && chown -R {SCULPTOR_USER}:{SCULPTOR_USER} {AGENT_DATA_PATH}",
            ),
        ]
        try:
            run_blocking(
                command=docker_on_create_command,
            )
        except ProcessError as e:
            raise SetupError(
                f"Failed to run container on_create_command:\nstderr:\n{e.stderr}\nstdout:\n{e.stdout}"
            ) from e

    sshd_log_file = "/tmp/sshd_log.txt"
    sshd_process = environment.run_process_in_background(
        ["/imbue/nix_bin/sshd", "-f", "/sshd_config/sshd_config", "-D", "-E", sshd_log_file], {}, run_as_root=True
    )
    while True:
        result = run_blocking(
            command=[
                "docker",
                "exec",
                "--user",
                "root",
                environment.container_id,
                "test",
                "-e",
                sshd_log_file,
            ],
            is_output_traced=False,
            is_checked=False,
        )
        if result.returncode == 0:
            break
        time.sleep(0.1)
    result = run_blocking(
        command=[
            "docker",
            "exec",
            "--user",
            "root",
            environment.container_id,
            "cat",
            sshd_log_file,
        ],
    )
    sshd_log = result.stdout
    if "Server listening on" not in sshd_log:
        raise SetupError(f"Immediate sshd startup check failed! log: {sshd_log}")

    sshd_stderr = sshd_process.read_stderr()
    if sshd_stderr != "":
        # This doesn't always catch failure to start the server. This is an optimistic check which
        # catches immediate failures and ignores failures that happen later.
        raise SetupError(f"Immediate sshd startup check failed! stderr: {sshd_stderr}")


def get_external_port_by_name_mapping(
    container_id: DockerContainerID, internal_port_by_server_name: dict[str, int]
) -> dict[str, int]:
    external_port_by_name = {}
    for server_name, internal_port in internal_port_by_server_name.items():
        try:
            external_port = _attempt_to_get_mapped_port(server_name, internal_port, container_id)
        except NoServerPortBoundError as e:
            log_exception(
                e,
                "Failed to get mapped port for server",
                priority=ExceptionPriority.MEDIUM_PRIORITY,
                extra=dict(server_name=server_name, internal_port=internal_port, container_id=container_id),
            )
            # note that we simply continue in this case, per note c70ca82b-f7b2-4beb-b2b4-0db777ad369b
            # the container will be brought online without the requested port.
        else:
            external_port_by_name[server_name] = external_port

    return external_port_by_name


def create_docker_container(create_command: list[str], docker_image: LocalDockerImage, name: str) -> DockerContainerID:
    with logger.contextualize(log_type=USER_FACING_LOG_TYPE):
        logger.info("Creating Docker container {}", name)
        logger.info("create_command: {}", create_command)
        try:
            try:
                create_container_result = run_blocking(command=create_command)
            except ProcessError as e:
                # sigh, have to handle the case where we try to start something with the same name
                # we have to be careful about how we detect this
                # because some strings are different in different docker versions and on different operating systems
                if "is already in use by container" in e.stderr and name in e.stderr:
                    logger.debug("Container name conflict, removing existing container and retrying: {}", name)
                    run_blocking(("docker", "rm", "-f", name))
                    create_container_result = run_blocking(command=create_command)
                else:
                    raise
        except ProcessError as e:
            stdout = e.stdout
            stderr = e.stderr
            if "Unable to find image" in stderr:
                raise ImageConfigError(
                    f"Docker image {docker_image.docker_image_tag} not found - exit code {e.returncode}: {stderr} {stdout}"
                ) from e
            if "Error response from daemon: Conflict. The container name " in stderr:
                raise ImageConfigError(
                    f"Docker container {name} already exists - exit code {e.returncode}: {stderr} {stdout}"
                ) from e
            raise ProviderError(f"Docker run failed with exit code {e.returncode}: {e.stderr} {e.stdout}") from e
    return DockerContainerID(create_container_result.stdout.strip())


def start_docker_container(container_id: DockerContainerID) -> None:
    with logger.contextualize(log_type=USER_FACING_LOG_TYPE):
        logger.info("Starting Docker container {}", container_id)
        try:
            run_blocking(command=["docker", "start", str(container_id)])
        except ProcessError as e:
            stdout = e.stdout
            stderr = e.stderr
            if stderr.startswith("Error response from daemon: No such container:"):
                raise EnvironmentNotFoundError(
                    f"Docker container {container_id} not found - exit code {e.returncode}: {stderr} {stdout}"
                ) from e
            raise ProviderError(f"Docker start failed with exit code {e.returncode}: {e.stderr} {e.stdout}") from e


def get_base_docker_create_args(name: str, internal_port_by_server_name: dict[str, int]) -> tuple[list[str], int, int]:
    port_args = flatten([("-p", f"127.0.0.1::{x}") for x in internal_port_by_server_name.values()])

    # On Linux, when claude creates files in the mounted directory, we need the files to be owned by the user running sculptor.
    # Otherwise, they'll appear as owned by root which will make it impossible to delete them later.
    user_id = os.getuid()
    group_id = os.getgid()

    # Create and start the container
    create_command = [
        *("docker", "run", "-td"),  # Detached mode
        *("--name", name),
        *("-v", f"checks_volume:{AGENT_DATA_PATH}"),
        # FIXME: are we sure this will never lead to user mismatch? shouldn't we handle this with user namespace? (see penlu for discussion)
        *("--user", f"{user_id}:{group_id}"),
        # A hacky way to ensure that the container has a writable home directory.
        *("-e", f"HOME={ROOT_PATH}"),
        # NOTE(bowei): sourced from https://github.com/anthropics/claude-code/blob/main/.devcontainer/Dockerfile
        *("-e", "NODE_OPTIONS=--max-old-space-size=4096"),
        *("-e", "POWERLEVEL9K_DISABLE_GITSTATUS=true"),
        # Let docker find an available ports for anything we want mapped
        *port_args,
        # Mounts the imbue control plane as RO volumes.
        # TODO: What is the right place to put this concern?
        *CONTROL_PLANE_VOLUME_DOCKER_ARGS,
    ]
    return create_command, group_id, user_id


def copy_code_repo(source_repo: Path, starting_branch: str | None = None) -> Path:
    new_code_dir = get_sculptor_folder() / "mounted_repo_copies" / uuid.uuid4().hex
    new_code_dir.mkdir(parents=True, exist_ok=True)
    _copy_repo_with_staging_and_branch(
        source_repo=source_repo, target_dir=new_code_dir, starting_branch=starting_branch
    )
    return new_code_dir


def destroy_outdated_docker_containers(environment_prefix: str) -> None:
    _handle_outdated_docker_containers(environment_prefix=environment_prefix, is_stopped=False)


def destroy_outdated_docker_images(environment_prefix: str) -> None:
    images = run_blocking(
        ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"], is_checked=False
    ).stdout.splitlines()

    targets = [img for img in images if img.startswith(f"{environment_prefix}-")]

    if targets:
        run_blocking(command=["docker", "rmi", *targets], is_checked=False)


def stop_outdated_docker_containers(environment_prefix: str) -> None:
    _handle_outdated_docker_containers(environment_prefix=environment_prefix, is_stopped=True)


def _handle_outdated_docker_containers(environment_prefix: str, is_stopped: bool) -> None:
    try:
        result = run_blocking(
            command=["docker", "ps", "-a", "--format", "{{.ID}} {{.Names}}"],
            timeout=30.0,
        )
    except ProcessSetupError as e:
        if e.__cause__ and "No such file or directory: 'docker'" in str(e.__cause__):
            raise DockerNotInstalledError("Docker does not exist or is not installed.") from e
        else:
            raise DockerError("Docker failed to list existing containers before even running") from e
    except ProcessError as e:
        raise DockerError("Docker failed to list existing containers") from e
    else:
        with ThreadPoolExecutor(max_workers=10, thread_name_prefix="DockerContainerStopper") as executor:
            futures: list[Future] = []
            for line in result.stdout.splitlines():
                container_id, container_name = line.strip().split(maxsplit=1)
                if container_name.startswith(environment_prefix):
                    if is_stopped:
                        futures.append(
                            executor.submit(
                                _stop_docker_container_and_ignore_if_docker_is_down, container_id=container_id
                            )
                        )
                    else:
                        futures.append(executor.submit(remove_docker_container, container_id=container_id))
            for future in futures:
                future.result()


def _stop_docker_container_and_ignore_if_docker_is_down(container_id: str) -> None:
    try:
        stop_docker_container(container_id=container_id)
    except ProviderIsDownError:
        pass


def _attempt_to_get_mapped_port(server_name: str, internal_port: int, container_id: str) -> int:
    """
    Returns the external port mapped to the internal port of a Docker container.

    Raises
        NoServerPortBoundError: If the port is not bound after several retries.
    """
    max_retries = 10
    for _ in range(max_retries):
        # Retry to handle race condition: Docker may need time to establish port mapping
        # after container creation before NetworkSettings.Ports is populated
        try:
            result = run_blocking(
                command=[
                    "docker",
                    "inspect",
                    "-f",
                    (
                        '{{ if index .NetworkSettings.Ports "'
                        + str(internal_port)
                        + '/tcp" }}{{ if index (index .NetworkSettings.Ports "'
                        + str(internal_port)
                        + '/tcp") 0 }}{{ (index (index .NetworkSettings.Ports "'
                        + str(internal_port)
                        + '/tcp") 0).HostPort }}{{ end }}{{ end }}'
                    ),
                    container_id,
                ],
                is_output_traced=False,
            )
        except ProcessError:
            # Docker inspect failed, treat as port not available
            result = None

        if result and result.stdout.strip():
            external_port = int(result.stdout.strip())
            logger.info("{} port for container {} is {}", server_name, container_id, external_port)
            return external_port
        time.sleep(0.1)
    raise NoServerPortBoundError(
        "Failed to get mapped port for {}, port {}, container ID {} after {} retries".format(
            server_name, internal_port, container_id, max_retries
        )
    )


def _copy_repo_with_staging_and_branch(
    source_repo: Path,
    target_dir: Path,
    starting_branch: str | None = None,
) -> None:
    """Copy repository with staged changes and create a new branch.

    It'll check out starting_branch to start from the right point."""

    # Clone repo and create branch
    try:
        # irritatingly, hardlinks don't work on modal, so we have to work around that here
        if os.environ.get("IMBUE_MODAL_INTEGRATION_TEST", "False").lower() in ("true", "1", "t"):
            hardlinks_arg = ["--no-hardlinks"]
        else:
            hardlinks_arg = []
        run_blocking(
            command=["git", "clone", *hardlinks_arg, str(source_repo), "."],
            cwd=target_dir,
        )
        logger.info("Copied cloned repo to {}", target_dir)
    except ProcessError:
        error_msg = f"Failed to clone repository from {source_repo}"
        logger.error(error_msg)
        raise

    if starting_branch is not None:
        logger.info("Checking out starting branch: {}", starting_branch)
        run_blocking(
            command=["git", "checkout", starting_branch],
            cwd=target_dir,
        )

    # Check if there are any staged changes to apply
    diff_check = run_blocking(
        command=["git", "diff", "--cached", "--quiet"],
        is_checked=False,
        is_output_traced=False,
        cwd=source_repo,
    )
    has_staged_changes = diff_check.returncode != 0

    # Only apply the patch if there are staged changes
    if has_staged_changes:
        git_diff_output = run_blocking(
            command=["git", "--no-pager", "diff", "--binary", "--cached"],
            cwd=source_repo,
        )
        with tempfile.NamedTemporaryFile(mode="w+") as patch_file:
            patch_file.write(git_diff_output.stdout)
            patch_file.flush()
            patch_file_path = patch_file.name
            logger.info("Applying staged changes from {}", patch_file_path)
            run_blocking(
                command=["git", "apply", "--index", patch_file_path],
                cwd=target_dir,
            )
    else:
        logger.info("No staged changes to apply")
