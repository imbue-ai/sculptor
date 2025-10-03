import time
from pathlib import Path
from threading import Event

import modal
import typer

from sculptor.cli.dev_commands.run_tests.constants import TEST_RUNNER_CPU
from sculptor.cli.dev_commands.run_tests.constants import TEST_RUNNER_RAM_MB
from sculptor.cli.dev_commands.run_tests.remote_test_class import write_test_names_to_sandbox
from sculptor.cli.dev_commands.run_tests.sandboxing import build_sandbox_in_app
from sculptor.cli.dev_commands.run_tests.sandboxing import launch_idempotent_process_in_sandbox
from sculptor.cli.dev_commands.run_tests.sandboxing import run_idempotent_process_in_sandbox
from sculptor.cli.dev_commands.run_tests.ssh_utils import get_code_rsync_command
from sculptor.cli.dev_commands.run_tests.ssh_utils import get_ssh_connection_command_as_args
from sculptor.interfaces.environments.v1.base import ModalEnvironmentConfig
from sculptor.interfaces.environments.v1.constants import CONTAINER_SSH_PORT
from sculptor.services.environment_service.providers.modal.app_context import use_modal_app


def make_sandbox_for_debugging(image_id: str, command: str | None = None, test_names: list[str] | None = None) -> None:
    sandbox_config = ModalEnvironmentConfig(
        unencrypted_ports=[CONTAINER_SSH_PORT],
        cpu=(TEST_RUNNER_CPU, TEST_RUNNER_CPU),
        memory=TEST_RUNNER_RAM_MB,
        # make this run for 2 hours at most -- the timeout below is 1, but this way there's a bit of slush for setup
        timeout=60 * 60 * 2,
    )
    keyfile = "science/secrets/physical/science.ed25519"
    # ensure the permissions are correct:
    if Path(keyfile).exists():
        Path(keyfile).chmod(0o600)
    else:
        typer.echo(
            "No SSH key found at science/secrets/physical/science.ed25519 -- you will only be able to connect if using an image that you created via run-tests -- is that what you wanted?  If so, simply hit enter."
        )
        keyfile = "modal_ssh_key"
        if Path(keyfile).exists():
            Path(keyfile).chmod(0o600)
    with use_modal_app("debugging", is_detached=False) as app:
        with modal.Volume.ephemeral(version=2) as vol:
            sandbox = build_sandbox_in_app(
                app, modal.Image.from_id(image_id), sandbox_config, volumes={"/data/myvol": vol}, keyfile=keyfile
            )
            sandbox_died_event = Event()
            ssh_connection_string = " ".join(
                get_ssh_connection_command_as_args(sandbox, keyfile=keyfile)
                + ["'cd /user_home/workspace && exec bash'"]
            )
            if command is not None:
                print("Writing command remotely...")
                with sandbox.open("/user_home/workspace/current_test.sh", "w") as f:
                    f.write(command)
            if test_names is not None:
                write_test_names_to_sandbox(sandbox, test_names, sandbox_died_event, keyfile)

            print("Connect here:")
            print("    " + ssh_connection_string)
            print("Sync with:")
            print("    " + " ".join(get_code_rsync_command(sandbox, keyfile=keyfile)))

            print()
            print("Starting docker for you...")

            docker_daemon = launch_idempotent_process_in_sandbox(
                sandbox,
                "rm -f /var/run/docker.pid /run/docker/containerd/containerd.pid /var/run/docker/containerd/containerd.pid /var/run/docker.sock && bash /start-dockerd.sh || (ip link delete docker0 && sleep 10 && bash /start-dockerd.sh)",
                sandbox_died_event,
                keyfile=keyfile,
            )

            # wait until docker is running (even though it really should be by this point)
            while True:
                _docker_info_check_exit, _stdout, _stderr = run_idempotent_process_in_sandbox(
                    sandbox, ["docker", "system", "info"], sandbox_died_event, is_logged=False, keyfile=keyfile
                )
                if _docker_info_check_exit == 0:
                    break
                if docker_daemon.poll() is not None:
                    raise RuntimeError(
                        "Docker daemon failed to start:\n"
                        + docker_daemon.read_stdout()
                        + "\n"
                        + docker_daemon.read_stderr()
                    )
                time.sleep(1.0)

            print("Docker is running!")

            print("Setting up images...")
            # FIXME(ab664a1e-8069-45cf-9a6c-6f528e33c31c): we also fetch the docker images here because modal does not include them in snapshots. Once they fix that this call to fetch-docker-data can be removed
            save_test_command_exit_code, save_test_command_stdout, save_test_command_stderr = (
                run_idempotent_process_in_sandbox(
                    sandbox,
                    f"cd /user_home/workspace/ && ( ( source ~/secrets.sh && PYTHONUNBUFFERED=1 uv run --no-sync --project sculptor python sculptor/sculptor/cli/dev.py fetch-docker-data | tee -a /tmp/setup.log ) 3>&1 1>&2 2>&3 | tee -a /tmp/setup.log ) 3>&1 1>&2 2>&3",
                    sandbox_died_event,
                )
            )
            if save_test_command_exit_code != 0:
                print(f"Failed to save test command: {save_test_command_stderr}\n{save_test_command_stdout}")

            print("Done setting up images!")

            time.sleep(12 * 60 * 60)
