import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from threading import Event

import modal
from loguru import logger

from imbue_core.processes.local_process import run_blocking
from sculptor.cli.dev_commands.run_tests.constants import TEST_RUNNER_CPU
from sculptor.cli.dev_commands.run_tests.constants import TEST_RUNNER_RAM_MB
from sculptor.cli.dev_commands.run_tests.sandboxing import build_sandbox_in_app
from sculptor.cli.dev_commands.run_tests.ssh_utils import ensure_ssh_key_for_modal
from sculptor.interfaces.environments.v1.base import ModalEnvironmentConfig
from sculptor.interfaces.environments.v1.constants import CONTAINER_SSH_PORT
from sculptor.primitives.constants import TEST_IMAGE_METADATA_CACHE_PATH
from sculptor.services.environment_service.providers.modal.app_context import use_modal_app
from sculptor.services.environment_service.providers.modal.new_image_builder import (
    build_image_from_dockerfile_contents,
)
from sculptor.utils.build_utils import get_current_build_metadata
from sculptor.utils.file_utils import copy_dir


def update_repo_copy(secrets: dict[str, str] | None, is_building_on_modal: bool = True) -> str | None:
    # check if the repo is dirty
    is_clean_result = run_blocking(["git", "status", "--porcelain"])
    if is_clean_result.stdout != "" or is_clean_result.stderr != "" or is_clean_result.returncode != 0:
        logger.info("Images can only be created from clean git states. Please commit or stash.", err=True)
        return None

    # make sure we have a key for building stuff
    ensure_ssh_key_for_modal()

    cached_repo_path = Path(os.path.expanduser("~/.imbue/image_cache/testing"))
    cached_repo_path.mkdir(parents=True, exist_ok=True)
    assert Path(".git").exists(), "Must be run from a git repo"
    cached_repo_location = cached_repo_path / ".git"
    if cached_repo_location.exists():
        logger.info("Deleting old cached git repo...")
        shutil.rmtree(cached_repo_location)

    logger.info("Caching git repo...")
    copy_dir(".git", cached_repo_location)

    logger.info("Repo cached. It is now safe to edit files again.")

    commit_hash = run_blocking(["git", "rev-parse", "HEAD"], cwd=cached_repo_path).stdout.strip()
    logger.info(f"Building image for {commit_hash}...")
    run_blocking(["git", "reset", "--hard"], cwd=cached_repo_path)
    # also need to remove any untracked files
    run_blocking(["git", "clean", "-fd"], cwd=cached_repo_path)
    if is_building_on_modal:
        with use_modal_app("josh-builder") as app:
            dockerfile_contents = (Path(cached_repo_path) / "sculptor" / "docker" / "Dockerfile.slim").read_text()
            assert secrets is None, (
                "No secrets should be passed when building on Modal, none are required, and setting them will mess with caching"
            )
            initial_image = build_image_from_dockerfile_contents(dockerfile_contents, cached_repo_path, secrets)
            initial_image = initial_image.dockerfile_commands(
                [
                    "COPY modal_ssh_key.pub /root/.ssh/",
                    "RUN cat /root/.ssh/modal_ssh_key.pub >> /root/.ssh/authorized_keys",
                ],
                context_dir=Path("."),
            )
            config = ModalEnvironmentConfig(
                unencrypted_ports=[CONTAINER_SSH_PORT],
                cpu=(TEST_RUNNER_CPU, TEST_RUNNER_CPU),
                memory=TEST_RUNNER_RAM_MB,
                timeout=60 * 60,
            )
            sandbox = build_sandbox_in_app(app, initial_image, config)
            sandbox_died_event = Event()
            logger.info(f"Created initial image on Modal: {initial_image.object_id}")

            logger.info("Now adding final layers...")

            # fine, we need to go update it (this step takes kind of a long time bc the images are large)
            # roughly 10-15 minutes right now
            final_image = _finalize_image_setup(sandbox, sandbox_died_event)

            # write out the resulting image id
            final_image_id = final_image.object_id
            Path("sculptor/docker/cached_modal_image_id.txt").write_text(str(final_image_id) + "\n")

            # update the cached data
            updated_modal_docker_cache_data = get_current_build_metadata()
            TEST_IMAGE_METADATA_CACHE_PATH.write_text(json.dumps(updated_modal_docker_cache_data, indent=2) + "\n")

            # tell the user that everything worked out
            logger.info(f"Success!  Created image on Modal: {final_image_id}")

            # shut down the sandbox
            sandbox.terminate()
    else:
        process = subprocess.Popen(
            [
                "depot",
                "build",
                "-f",
                "sculptor/docker/Dockerfile.slim",
                "-t",
                f"joshalbrecht/generally_intelligent:{commit_hash}",
                "--push",
                ".",
            ],
            cwd=cached_repo_path,
            env={**os.environ},
            stdin=subprocess.DEVNULL,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        exit_code = process.wait()
        if exit_code != 0:
            logger.info("Failed to build image", err=True)
            return None

        logger.warning(
            "This does not do any caching of docker layers for the inner docker!  So this probably won't work anymore..."
        )

    # save it for others to be able to use
    Path("sculptor/docker/cached_image_hash.txt").write_text(commit_hash + "\n")

    logger.info(f"Success!  Created image for commit: {commit_hash}")
    return commit_hash


def _finalize_image_setup(sandbox: modal.Sandbox, sandbox_died_event: Event) -> modal.Image:
    """
    Runs the make-default-docker-images command, which ensures that we have layers cached when testing
    """
    #
    # # now we can start the docker daemon
    # logger.info("Starting docker daemon (required for this step)...")
    # _docker_daemon = launch_idempotent_process_in_sandbox(
    #     sandbox, "bash /start-dockerd.sh >& /tmp/docker.log", sandbox_died_event
    # )
    #
    # # wait until docker is running (even though it really should be by this point)
    # logger.info("Waiting for docker to start...")
    # while True:
    #     _docker_info_check_exit, _stdout, _stderr = run_idempotent_process_in_sandbox(
    #         sandbox, ["docker", "system", "info"], sandbox_died_event
    #     )
    #     if _docker_info_check_exit == 0:
    #         break
    #     time.sleep(1.0)
    #
    # # fetch and tag the main image
    # logger.info("Fetching and tagging main docker layer...")
    # exit_code, stdout, stderr = run_idempotent_process_in_sandbox(
    #     sandbox,
    #     "cd /user_home/workspace/ && docker pull ghcr.io/imbue-ai/sculptorbase_nix:20250916@sha256:ea70c3d9ff68558328e8be8d0aa43b67607aaf0d075e352e2291535a83ee230d && docker image tag ghcr.io/imbue-ai/sculptorbase_nix:20250916@sha256:ea70c3d9ff68558328e8be8d0aa43b67607aaf0d075e352e2291535a83ee230d ghcr.io/imbue-ai/sculptorbase_nix:current",
    #     sandbox_died_event,
    # )
    # if not exit_code == 0:
    #     logger.error(f"Failed to fetch nix image: stdout=\n{stdout}\nstderr=\n{stderr}")
    #     raise RuntimeError("Failed to fetch nix image")
    #
    # # finally, run the make default images command
    # logger.info("Running make-default-docker-images...")
    # exit_code, stdout, stderr = run_idempotent_process_in_sandbox(
    #     sandbox,
    #     "cd /user_home/workspace/ && uv run --no-sync --project sculptor python sculptor/sculptor/cli/dev.py make-default-docker-images",
    #     sandbox_died_event,
    # )
    # if not exit_code == 0:
    #     logger.error(f"Failed to run make-default-docker-images: stdout=\n{stdout}\nstderr=\n{stderr}")
    #     raise RuntimeError("Failed to run make-default-docker-images")

    # and snapshot the filesystem so that we have a new image with all the layers cached
    # really shouldn't take longer than that...
    logger.info("Snapshotting the final image...")
    start_time = time.monotonic()
    image = sandbox.snapshot_filesystem(timeout=5 * 60)
    end_time = time.monotonic()
    logger.info(f"Snapshotting the integration test image took {end_time - start_time:.1f} seconds")
    logger.debug(f"Final image ID is {image.object_id}")

    # peacefully close the sandbox
    sandbox_died_event.set()
    sandbox.terminate()

    return image
