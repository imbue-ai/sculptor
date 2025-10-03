"""
Example command to update the docker images:
```sh
uv run sculptor/sculptor/cli/dev.py refresh-image
```

# Publish images to CloudFront CDN via S3:
```sh
uv run sculptor/sculptor/cli/dev.py publish-control-plane-and-default-dev-container-to-s3
```
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated

import boto3
import typer
from loguru import logger

from imbue_core.git import get_git_repo_root
from imbue_core.itertools import only
from imbue_core.processes.local_process import run_blocking
from sculptor.cli.dev_commands.common import upload_file
from sculptor.cli.dev_commands.make_default_docker_images import make_default_images
from sculptor.cli.dev_commands.refresh_image import update_repo_copy
from sculptor.cli.dev_commands.run_test_image import make_sandbox_for_debugging
from sculptor.cli.dev_commands.run_test_in_ci import run_test_in_ci_implementation
from sculptor.cli.dev_commands.run_tests.main import run_all_tests
from sculptor.primitives.constants import CONTROL_PLANE_MANIFEST_PATH
from sculptor.primitives.constants import CONTROL_PLANE_TAG_PATH
from sculptor.services.environment_service.providers.docker.devcontainer_image_builder import (
    get_default_devcontainer_image_reference,
)
from sculptor.services.environment_service.providers.docker.devcontainer_image_builder import (
    start_control_plane_background_setup,
)
from sculptor.services.environment_service.providers.docker.image_utils import docker_image_url_to_s3_safe_name
from sculptor.services.environment_service.providers.docker.volume_mounted_nix_control_plane import (
    CONTROL_PLANE_IMAGE_URL,
)

CONTROL_PLANE_REQUIRED_SUBPROJECTS = (
    "imbue",
    "imbue_core",
    "imbue_cli",
    "imbue_tools",
    "imbue_verify",
    "imbue_retrieve",
)

typer_cli = typer.Typer(
    name="sculptor_dev",
    help="A set of tools for developing Sculptor itself.",
    no_args_is_help=True,
    invoke_without_command=False,
    pretty_exceptions_enable=False,
)


def _get_registry_secrets() -> dict[str, str]:
    assert "REGISTRY_PASSWORD" in os.environ and "REGISTRY_USERNAME" in os.environ
    return dict(
        REGISTRY_PASSWORD=os.environ["REGISTRY_PASSWORD"],
        REGISTRY_USERNAME=os.environ["REGISTRY_USERNAME"],
    )


@typer_cli.command(help="Build the base Docker image for Sculptor based on the current git commit.")
def refresh_image(is_building_on_modal: bool = True) -> None:
    secrets = None if is_building_on_modal else _get_registry_secrets()
    update_repo_copy(secrets, is_building_on_modal)


@typer_cli.command(help="Used to build our default Docker images during integration testing.")
def make_default_docker_images() -> None:
    make_default_images()


def _download_from_s3(client, s3_path: str, local_path: str) -> None:
    bucket_name = s3_path.split("/")[2]
    key = "/".join(s3_path.split("/")[3:])
    logger.info("Downloading {} to {}", s3_path, local_path)
    client.download_file(bucket_name, key, local_path)
    logger.info("Finished downloading {} to {}", s3_path, local_path)


@typer_cli.command(help="Ensure that we have all of the docker data we need.")
def fetch_docker_data() -> None:
    threads = start_control_plane_background_setup(thread_suffix="FetchDockerData")
    # we need to wait for the threads to make sure we get docker data set up ahead of the tests
    for thread in threads:
        thread.join()


@typer_cli.command(help="Runs a sandbox so that you can easily debug a test")
def run_test_image(image_id: str) -> None:
    make_sandbox_for_debugging(image_id)


@typer_cli.command(
    help="Runs a sandbox for a single test when we were not able to snapshot properly (starts from the start, no artifacts present)"
)
def run_single_test(
    image_id: str, test_names: Annotated[str, typer.Option()], command: Annotated[str, typer.Option()]
) -> None:
    make_sandbox_for_debugging(image_id, command=command, test_names=list(test_names.split(",")))


@typer_cli.command(help="Run tests remotely in parallel using Modal.")
def run_tests(
    is_using_modal_base_image: bool = True,
    is_waiting_on_failure: bool = True,
    unit_test_runner_count: int = 4,
    test_names: str | None = None,
    is_running_integration: bool = True,
    enable_sentry: bool = False,
) -> None:
    secrets = None if is_using_modal_base_image else _get_registry_secrets()
    restrict_to_test_names = None if test_names is None else set(test_names.split(","))
    exit_code = run_all_tests(
        secrets,
        is_using_modal_base_image=is_using_modal_base_image,
        is_waiting_on_failure=is_waiting_on_failure,
        unit_test_runner_count=unit_test_runner_count,
        restrict_to_test_names=restrict_to_test_names,
        is_running_integration=is_running_integration,
        enable_sentry=enable_sentry,
    )
    if exit_code == 0:
        logger.success("All tests passed!")
    elif exit_code == 34:
        logger.success("All tests passed, though some were flaky or slow.")
        os._exit(34)
    else:
        logger.error("Some tests failed.")
    raise typer.Exit(exit_code)


# TODO: this could be extended to update specific snapshots rather than all of them...
@typer_cli.command(help="Update all snapshots on modal")
def update_snapshots(test_names: str | None = None) -> None:
    restrict_to_test_names = None if test_names is None else set(test_names.split(","))
    exit_code = run_all_tests(
        secrets=None,
        is_using_modal_base_image=True,
        is_waiting_on_failure=True,
        is_updating_snapshots=True,
        restrict_to_test_names=restrict_to_test_names,
    )
    if exit_code == 0:
        logger.success("All snapshots updated!")
    else:
        logger.error("Some snapshots failed to update.")
        raise typer.Exit(1)


@typer_cli.command(
    help="Run test in CI. Use like this:\n    dev.py run-test-in-ci COMMAND_ID --args --for --pytest\n(ie, all args after COMMAND_ID will be passed directly to pytest)"
)
def run_test_in_ci(command_id: str, pytest_args: list[str]) -> None:
    run_test_in_ci_implementation(command_id, pytest_args)


def _save_and_upload_image(image_url: str, image_type: str, platform: str, client) -> None:
    """Save a Docker image and upload it to S3 for a specific platform."""
    logger.info(f"Processing {image_type} image for {platform} platform: {image_url}")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_file_path = Path(temp_dir) / "docker_save.tar"

        # Pull the image for the specified platform
        pull_cmd = f"docker pull --platform linux/{platform} {image_url}"
        logger.info("Running: {}", pull_cmd)
        pull_result = os.system(pull_cmd)
        if pull_result != 0:
            raise RuntimeError(f"Failed to pull {image_url} for platform {platform}")

        # Save the image to tar file
        save_cmd = f"docker save {image_url} -o {str(temp_file_path)}"
        logger.info("Running: {}", save_cmd)
        save_result = os.system(save_cmd)
        if save_result != 0:
            raise RuntimeError(f"Failed to save {image_url}")

        # Upload to S3 with safe name that includes image URL and platform
        safe_name = docker_image_url_to_s3_safe_name(image_url, platform)
        s3_path = f"s3://imbue-sculptor-latest/images/{safe_name}.tar"
        logger.info("Uploading to: {}", s3_path)
        upload_file(temp_file_path, f"images/{safe_name}.tar", "imbue-sculptor-latest", client)
        logger.success("Successfully uploaded image to S3: {}", s3_path)


@typer_cli.command(help="Build/publish/upload the control plane")
def build_control_plane(use_depot: bool = True, debug: bool = False) -> None:
    # when we're not debugging, we must be committed
    suffix = ""
    is_clean_result = run_blocking(["git", "status", "--porcelain"])
    if is_clean_result.stdout != "" or is_clean_result.stderr != "" or is_clean_result.returncode != 0:
        if debug:
            suffix = "-dirty"
        else:
            raise RuntimeError("Git working directory is not clean. Please commit or stash changes first.")
    assert Path(".git").exists(), "This command must be run from the git repo root"
    project_files_dir = Path("sculptor/claude-container/build/project-files")
    project_files_dir.mkdir(parents=True, exist_ok=True)
    for filename in ("pyproject.toml", "uv.lock"):
        shutil.copy(filename, str(project_files_dir / filename))
    sub_projects = CONTROL_PLANE_REQUIRED_SUBPROJECTS
    for sub_project in sub_projects:
        sub_project_dir = project_files_dir / sub_project
        sub_project_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(str(Path(sub_project) / "pyproject.toml"), str(sub_project_dir / "pyproject.toml"))
    run_blocking(
        [
            "git",
            "archive",
            "--format=zip",
            "-o",
            "sculptor/claude-container/build/control-plane-src.zip",
            "HEAD",
            *sub_projects,
        ]
    )
    commit_hash = run_blocking(["git", "rev-parse", "HEAD"]).stdout.strip() + suffix
    git_branch = run_blocking(["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
    user_name = run_blocking(["id", "-un"]).stdout.strip()
    build_time = run_blocking(["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"]).stdout.strip()
    last_commit_date = run_blocking(["git", "log", "-1", "--date=format:%Y%m%d", "--format=%cd"]).stdout.strip()
    last_commit_time = run_blocking(["git", "log", "-1", "--format=%cI"]).stdout.strip()
    hostname = run_blocking(["hostname"]).stdout.strip()
    image_ghcr_tag_url = f"ghcr.io/imbue-ai/sculptorbase_nix:{commit_hash}"
    builder = ["depot"] if use_depot else ["docker", "buildx"]
    build_args = [
        *builder,
        "build",
        *("-f", "sculptor/claude-container/Dockerfile.base_nix"),
        *("--build-arg", f'_IMBUE_BUILT_FROM_GIT_HASH="{commit_hash}"'),
        *("--build-arg", f'_IMBUE_BUILT_FROM_GIT_BRANCH="{git_branch}"'),
        *("--build-arg", f'_IMBUE_BUILT_BY_USER="{user_name}"'),
        *("--build-arg", f'_IMBUE_BUILT_AT_TIMESTAMP="{build_time}"'),
        *("--build-arg", f'_IMBUE_BUILT_AT_LAST_COMMIT_DATE="{last_commit_date}"'),
        *("--build-arg", f'_IMBUE_BUILT_AT_LAST_COMMIT_TIMESTAMP="{last_commit_time}"'),
        *("--build-arg", f'_IMBUE_BUILT_ON_HOSTNAME="{hostname}"'),
        *("--platform", "linux/amd64,linux/arm64"),
        "sculptor/claude-container/",
    ]
    if use_depot:
        build_args.extend(["-t", image_ghcr_tag_url, "--push", "--save"])
    else:
        build_args.extend(
            [
                "-t",
                image_ghcr_tag_url,
                "--push",
                *("--build-arg", "BUILDKIT_INLINE_CACHE=1"),
                "--cache-to=type=registry,ref=ghcr.io/imbue-ai/scuptorbase_nix_buildcache:buildcache,mode=max",
                "--cache-from=type=registry,ref=ghcr.io/imbue-ai/scuptorbase_nix_buildcache:buildcache",
            ]
        )
    process = subprocess.Popen(
        build_args,
        env=None if use_depot else {**os.environ, "DOCKER_BUILDKIT": "1"},
        stdin=subprocess.DEVNULL,
        stderr=sys.stderr,
        stdout=sys.stdout,
    )
    exit_code = process.wait()
    assert exit_code == 0, "Docker build failed"

    client = boto3.client("s3")
    manifest_obj = json.loads(run_blocking(["docker", "manifest", "inspect", image_ghcr_tag_url]).stdout)
    manifests = manifest_obj["manifests"]
    platforms = ["arm64", "amd64"]
    futures = []
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="DockerDownloader") as executor:
        for platform in platforms:
            manifest = only(x for x in manifests if x["platform"]["architecture"] == platform)
            digest = manifest["digest"]
            control_plane_image_url = f"{image_ghcr_tag_url}@{digest}"
            logger.info(f"Starting upload of Docker control plane images to S3: {control_plane_image_url}")
            f = executor.submit(_save_and_upload_image, control_plane_image_url, "control_plane", platform, client)
            futures.append(f)
    # raise any exceptions
    for f in futures:
        f.result()

    logger.success("Successfully published control plane image to S3!")

    # finally, write the tag and sha to the appropriate files
    (get_git_repo_root() / CONTROL_PLANE_TAG_PATH).write_text(commit_hash + "\n")
    (get_git_repo_root() / CONTROL_PLANE_MANIFEST_PATH).write_text(json.dumps(manifest_obj) + "\n")


@typer_cli.command(help="Publish control plane and default dev container to S3 for both arm64 and amd64 platforms.")
def publish_control_plane_and_default_dev_container_to_s3() -> None:
    """
    Publish both control plane and default dev container images to S3.
    Creates 4 files total: [control_plane, default_devcontainer] x [arm64, amd64]
    """
    control_plane_image = CONTROL_PLANE_IMAGE_URL
    default_devcontainer_image = get_default_devcontainer_image_reference()
    client = boto3.client("s3")

    platforms = ["arm64", "amd64"]
    images_to_process = [
        (control_plane_image, "control_plane"),
        (default_devcontainer_image, "default_devcontainer"),
    ]

    logger.info("Starting upload of Docker images to S3...")
    logger.info(f"Control plane image: {control_plane_image}")
    logger.info(f"Default devcontainer image: {default_devcontainer_image}")

    # Process each combination of image and platform
    for image_url, image_type in images_to_process:
        for platform in platforms:
            _save_and_upload_image(image_url, image_type, platform, client)

    logger.success("Successfully published all images to S3!")


if __name__ == "__main__":
    if sys.argv[1] == "run-test-in-ci":
        run_test_in_ci(sys.argv[2], sys.argv[3:])
    else:
        typer_cli()
