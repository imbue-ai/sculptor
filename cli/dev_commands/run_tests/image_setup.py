import time
from threading import Event
from typing import Sequence
from typing import cast

import modal
import typer
from grpclib import GRPCError
from loguru import logger

from imbue_core.async_monkey_patches import log_exception
from imbue_core.processes.errors import EnvironmentStoppedError
from imbue_core.processes.errors import ShutdownError
from imbue_core.processes.local_process import RunningProcess
from sculptor.cli.dev_commands.run_tests.discovery import find_all_tests
from sculptor.cli.dev_commands.run_tests.retry_logic import retry_sandbox_command
from sculptor.cli.dev_commands.run_tests.sandboxing import SandboxDeathEvent
from sculptor.cli.dev_commands.run_tests.sandboxing import build_sandbox_in_app
from sculptor.cli.dev_commands.run_tests.sandboxing import handle_sandbox_failure
from sculptor.cli.dev_commands.run_tests.sandboxing import launch_idempotent_process_in_sandbox
from sculptor.interfaces.environments.v1.base import ModalEnvironmentConfig


@retry_sandbox_command
def create_test_images_on_modal_and_load_tests(
    app,
    base_modal_image: modal.Image,
    sandbox_config: ModalEnvironmentConfig,
    on_basic_image_complete,
    is_skipping_flaky_tests: bool,
) -> tuple[modal.Image | None, modal.Image | None, list[str]]:
    """
    The fact that this both creates images and loads tests is simply an optimization -- we overlap the two
    activities to save time.
    """

    sandbox: modal.Sandbox | None = None
    sandbox_died_event = Event()
    try:
        sandbox = build_sandbox_in_app(app, base_modal_image, sandbox_config, is_docker_enabled=True)
        sandbox_died_event = cast(Event, SandboxDeathEvent(sandbox, Event()))
        npm_install, python_install = _get_install_commands(sandbox, sandbox_died_event, is_sequential=True)

        # minor optimization, we run this while waiting for the remote to finish installation
        unit_test_files = find_all_tests("sculptor/sculptor", is_skipping_flaky_tests)

        # wait for the installations to finish
        failed_install = _get_first_failure([npm_install, python_install])
        if failed_install is not None:
            typer.echo(
                f"Failed to install dependencies (exit code={failed_install.returncode})\nstdout={failed_install.read_stdout()}\nstderr={failed_install.read_stderr()}",
                err=True,
            )
            return None, None, []

        # then snapshotting the resulting image
        modal_image = sandbox.snapshot_filesystem()

        # uses a callback so that we can start the unit tests earlier
        on_basic_image_complete(modal_image, unit_test_files)

        typer.echo("Running stupid build commands...")
        # now do the builds for integration
        make_commands = _get_make_commands(sandbox, sandbox_died_event)
        # this is shoved here because we've got some time and it takes a little bit of time
        all_integration_tests = find_all_tests("sculptor/tests/integration", is_skipping_flaky_tests)
        # wait for the build commands to finish
        failed_make_command = _get_first_failure(make_commands)
        if failed_make_command is not None:
            typer.echo(
                f"Failed to build (exit code={failed_make_command.returncode})\nstdout={failed_make_command.read_stdout()}\nstderr={failed_make_command.read_stderr()}",
                err=True,
            )
            return modal_image, None, []

        # really shouldn't take longer than that...
        start_time = time.monotonic()
        integration_test_image = sandbox.snapshot_filesystem(timeout=5 * 60)
        end_time = time.monotonic()
        logger.info(f"Snapshotting the integration test image took {end_time - start_time:.1f} seconds")

        # peacefully close the sandbox
        sandbox_died_event.set()
        sandbox.terminate()

        return modal_image, integration_test_image, all_integration_tests
    except EnvironmentStoppedError:
        raise
    except Exception as e:
        if not isinstance(e, (ShutdownError, GRPCError)):
            log_exception(e, "Failed to create test images on modal and load tests")
        sandbox_died_event.set()
        handle_sandbox_failure(sandbox, e, is_known_sandbox_failure=isinstance(e, GRPCError))
    assert False, "Should never get here"


def _get_install_commands(
    sandbox: modal.Sandbox, sandbox_died_event: Event, is_sequential: bool = False
) -> tuple[RunningProcess, RunningProcess]:
    python_install = launch_idempotent_process_in_sandbox(
        sandbox,
        "cd /user_home/workspace && unset UV_INDEX_URL && UV_LINK_MODE=copy uv sync --project sculptor --dev --active --locked --all-extras",
        sandbox_died_event,
    )
    # FIXME: this is only needed because uv is dumb -- when npm packages are being installed, it will sometimes fail
    #  with some stupid error about the node_modules not being found.  I tried excluding that directory from uv, but
    #  couldn't find a way to get it to actually shut up about it, so, whatever, they're sequential for now
    if is_sequential:
        python_install.wait()
    npm_install = launch_idempotent_process_in_sandbox(
        sandbox,
        "cd /user_home/workspace && source ~/.nvm/nvm.sh && cd sculptor/frontend && nvm use && npm install",
        sandbox_died_event,
    )
    return npm_install, python_install


def _get_make_commands(sandbox: modal.Sandbox, sandbox_died_event: Event) -> list[RunningProcess]:
    make_commands = [
        launch_idempotent_process_in_sandbox(
            sandbox,
            "cd /user_home/workspace/sculptor && make build-backend",
            sandbox_died_event,
        ),
        launch_idempotent_process_in_sandbox(
            sandbox,
            "cd /user_home/workspace && source ~/.nvm/nvm.sh && cd sculptor/frontend && nvm use && cd .. && make actually-build-frontend",
            sandbox_died_event,
        ),
    ]
    return make_commands


def _get_first_failure(modal_processes: Sequence[RunningProcess]) -> RunningProcess | None:
    mutable_modal_processes = list(modal_processes)
    while len(mutable_modal_processes) > 0:
        for proc in mutable_modal_processes:
            if proc.poll() is not None:
                if proc.returncode != 0:
                    return proc
                mutable_modal_processes.remove(proc)
    return None
