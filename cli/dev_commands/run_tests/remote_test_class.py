import os
import time
from pathlib import Path
from threading import Event
from threading import Lock
from typing import Callable
from typing import cast
from uuid import uuid4
from xml.etree import ElementTree

import modal
from grpclib import GRPCError
from loguru import logger

from imbue_core.async_monkey_patches import log_exception
from imbue_core.constants import ExceptionPriority
from imbue_core.processes.errors import EnvironmentStoppedError
from imbue_core.processes.errors import ShutdownError
from imbue_core.processes.local_process import run_blocking
from imbue_core.processes.remote_process import RemoteRunningProcess
from imbue_core.subprocess_utils import ProcessSetupError
from imbue_core.thread_utils import ObservableThread
from sculptor.cli.dev_commands.run_tests.constants import REMOTE_JUNIT_PATH
from sculptor.cli.dev_commands.run_tests.reporting import add_output_links_to_report
from sculptor.cli.dev_commands.run_tests.reporting import add_repro_command_to_report
from sculptor.cli.dev_commands.run_tests.reporting import create_junit_report_for_single_test
from sculptor.cli.dev_commands.run_tests.retry_logic import retry_sandbox_command
from sculptor.cli.dev_commands.run_tests.sandboxing import SandboxDeathEvent
from sculptor.cli.dev_commands.run_tests.sandboxing import build_sandbox_in_app
from sculptor.cli.dev_commands.run_tests.sandboxing import handle_sandbox_failure
from sculptor.cli.dev_commands.run_tests.sandboxing import launch_idempotent_process_in_sandbox
from sculptor.cli.dev_commands.run_tests.sandboxing import run_idempotent_process_in_sandbox
from sculptor.cli.dev_commands.run_tests.sandboxing import safely_terminate_sandbox
from sculptor.cli.dev_commands.run_tests.ssh_utils import get_code_rsync_command
from sculptor.cli.dev_commands.run_tests.ssh_utils import get_ssh_connection_command_as_args
from sculptor.interfaces.environments.v1.base import ModalEnvironmentConfig
from sculptor.services.environment_service.providers.modal.app_context import ModalAppWithOutputBuffer


class RemoteTest:
    def __init__(
        self,
        commit_hash: str,
        modal_image: modal.Image,
        sandbox_config: ModalEnvironmentConfig,
        test_args: list[str],
        app: ModalAppWithOutputBuffer,
        is_unit: bool,
        on_failure: Callable[["RemoteTest"], str | None],
        is_waiting_on_failure: bool,
        is_updating_snapshots: bool,
        flake_index: int | None = None,
    ) -> None:
        if not is_unit:
            # we still make a junit file, just so that we can know when we're done
            # but importantly we capture the output ourselves
            # also, we skip build artifacts for integration tests (it's not a valid arg for unit tests)
            capture_args = ["-s", "--skip-build-artifacts"]
        else:
            # capture output in junit
            capture_args = ["-o", "junit_logging=all"]
        capture_str = " ".join(capture_args)
        command_id = uuid4().hex
        snapshot_update_flag = "--snapshot-update" if is_updating_snapshots else ""
        if flake_index is None:
            commit_hash_str = commit_hash
        else:
            commit_hash_str = f"CI_COMMIT_SHA={commit_hash}_flake_{flake_index}"
        command = f"source ~/secrets.sh && source ~/.nvm/nvm.sh && cd /user_home/workspace/sculptor/frontend && nvm use && cd ../.. && CI_COMMIT_SHA={commit_hash_str} CI_JOB_NAME={os.getenv('CI_JOB_NAME')} CI_JOB_ID={os.getenv('CI_JOB_ID')} PYTHONUNBUFFERED=1 IMBUE_MODAL_INTEGRATION_TEST=1 UV_LINK_MODE=copy uv run --no-sync --project sculptor sculptor/sculptor/cli/dev.py run-test-in-ci {command_id} -v {capture_str} --junitxml={REMOTE_JUNIT_PATH} --tracing=retain-on-failure --video=retain-on-failure --screenshot=only-on-failure --durations=0 --durations-min=0.05 {snapshot_update_flag} --snapshot-details --snapshot-warn-unused --cov=. --cov-report=xml:/tmp/coverage.xml @tests_to_run.txt"

        self.flake_index = flake_index
        self.flake_processes = []
        self.test_args = test_args
        self.is_unit = is_unit
        self.commit_hash = commit_hash
        self.sandbox_died_event: Event | None = None
        self.sandbox: modal.Sandbox | None = None
        self.modal_image = modal_image
        self.sandbox_config = sandbox_config
        self.app = app
        self.sandbox_count = 0
        self.process: RemoteRunningProcess | None = None
        self.creation_time: float = time.monotonic()
        self.start_time: float | None = None
        self.end_time: float | None = None
        self.duration: float | None = None
        self.repro_command: str | None = None
        self.junit_report: ElementTree.Element | None = None
        self.final_junit_report: ElementTree.Element | None = None
        self.final_junit_report_lock = Lock()
        self.failed = False
        self.phase = "starting"
        self.exit_code: int | None = None
        self.on_failure = on_failure
        self.is_waiting_on_failure = is_waiting_on_failure
        self.is_updating_snapshots = is_updating_snapshots
        self.command = command
        self._command_id = command_id
        self._sandbox_thread = ObservableThread(target=self.run, args=(modal_image, sandbox_config, app))
        self._stop_event = Event()
        self._sandbox_thread.start()

    def is_thread_done(self):
        return not self._sandbox_thread.is_alive()

    def get_effective_duration(self) -> float:
        return self.duration or (time.monotonic() - (self.start_time or self.creation_time))

    def launch_flake_test(self, index: int) -> "RemoteTest":
        """Launch another instance of this test to see if it flakes."""
        test = RemoteTest(
            commit_hash=self.commit_hash,
            modal_image=self.modal_image,
            sandbox_config=self.sandbox_config,
            test_args=self.test_args,
            app=self.app,
            is_unit=self.is_unit,
            on_failure=_no_op_on_failure,
            is_waiting_on_failure=False,
            is_updating_snapshots=False,
            flake_index=index,
        )
        self.flake_processes.append(test)
        return test

    def get_name(self) -> str:
        if len(self.test_args) == 1:
            name = self.test_args[0]
        else:
            # otherwise, probably a bunch of files
            files = []
            for arg in self.test_args:
                if "/" in arg:
                    files.append(arg.split("/")[-1])
            name = f"{len(self.test_args)} unit tests, including ({', '.join(files[:3])}...)"
        if self.flake_index is not None:
            name += f" (flake {self.flake_index})"
        return name

    @retry_sandbox_command
    def run(self, modal_image: modal.Image, sandbox_config: ModalEnvironmentConfig, app: ModalAppWithOutputBuffer):
        if self._stop_event.is_set():
            self.phase = "stopped_by_event"
            return
        if self.exit_code is not None:
            return
        self.phase = "sandbox_setup"
        self.sandbox = None
        self.sandbox_died_event = Event()
        self.process = None
        self.exit_code = None
        try:
            self.sandbox_count += 1
            self.sandbox = build_sandbox_in_app(app, modal_image, sandbox_config)
            self.sandbox_died_event = cast(Event, SandboxDeathEvent(self.sandbox, self.sandbox_died_event))

            if self._stop_event.is_set():
                self.phase = "stopped_by_event"
                self.sandbox.terminate()
                return

            # *now* we can start the docker daemon
            docker_daemon = launch_idempotent_process_in_sandbox(
                self.sandbox,
                "rm -f /var/run/docker.pid /run/docker/containerd/containerd.pid /var/run/docker/containerd/containerd.pid /var/run/docker.sock && bash /start-dockerd.sh || (ip link delete docker0 && sleep 10 && bash /start-dockerd.sh)",
                self.sandbox_died_event,
            )

            # dump the test command to the filesystem for easier future debugging:
            # (but make sure that, if you run it, it would not accidentally overwrite the uploaded data)
            command_env_arg_to_replace_for_debugging = f"CI_JOB_NAME={os.getenv('CI_JOB_NAME')}"
            assert self.command.count(command_env_arg_to_replace_for_debugging) == 1, (
                f"Expected exactly one occurrence of {command_env_arg_to_replace_for_debugging} in {self.command}, found {self.command.count(command_env_arg_to_replace_for_debugging)}"
            )
            command_to_log_for_debugging = self.command.replace(
                command_env_arg_to_replace_for_debugging, "CI_JOB_NAME=debugging"
            )
            # FIXME(ab664a1e-8069-45cf-9a6c-6f528e33c31c): we also fetch the docker images here because modal does not include them in snapshots. Once they fix that this call to fetch-docker-data can be removed
            save_test_command_exit_code, save_test_command_stdout, save_test_command_stderr = (
                run_idempotent_process_in_sandbox(
                    self.sandbox,
                    f"echo 'export ALLOW_DEBUG_INPUT=1' > /user_home/workspace/current_test.sh && echo '{command_to_log_for_debugging}' >> /user_home/workspace/current_test.sh && chmod +x /user_home/workspace/current_test.sh && cd /user_home/workspace/ && ( ( source ~/secrets.sh && PYTHONUNBUFFERED=1 uv run --no-sync --project sculptor python sculptor/sculptor/cli/dev.py fetch-docker-data | tee -a /tmp/setup.log ) 3>&1 1>&2 2>&3 | tee -a /tmp/setup.log ) 3>&1 1>&2 2>&3",
                    self.sandbox_died_event,
                )
            )
            assert save_test_command_exit_code == 0, (
                f"Failed to save test command: {save_test_command_stderr}\n{save_test_command_stdout}"
            )

            write_test_names_to_sandbox(self.sandbox, self.test_args, self.sandbox_died_event)

            # wait until docker is running (even though it really should be by this point)
            while True:
                _docker_info_check_exit, _stdout, _stderr = run_idempotent_process_in_sandbox(
                    self.sandbox, ["docker", "system", "info"], self.sandbox_died_event, is_logged=False
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

            if self._stop_event.is_set():
                self.phase = "stopped_by_event"
                self.sandbox.terminate()
                return

            self.phase = "running_test"

            logger.info(f"Running: {self.test_args}")
            self.start_time = time.monotonic()
            self.process = launch_idempotent_process_in_sandbox(
                self.sandbox, self.command, self.sandbox_died_event, self._command_id
            )
            # this starts the streaming
            _output_queue = self.process.get_queue()

            # now we just wait for the process to finish and keep calculating the resulting junit report
            while self.process.poll() is None:
                self.junit_report = self.get_junit_report(is_final=False)
                self.process._thread.join(5.0)
            exit_code = self.process.wait()
            # just saving for reporting
            self.exit_code = exit_code

            self.phase = "test_complete"

            self.end_time = time.monotonic()
            self.duration = self.end_time - self.start_time
            logger.debug(
                f"Test {self._command_id} finished with exit code {exit_code} after {self.duration:.1f} seconds: {self.test_args}"
            )

            # if we failed, go take a snapshot and note the failure
            if exit_code != 0:
                self.repro_command = self.on_failure(self)
            # or if this is a flake test, we'll want to try to snapshot no matter what
            # this makes it easier to compare between runs that succeeded and those that failed
            elif self.flake_index is not None:
                self.repro_command, _rsync_command, _ssh_connection_string = snapshot_failure(self)

            self.phase = "sandbox_snapshots_complete"

            # if we succeeded, update our test snapshots
            if exit_code == 0 and self.is_updating_snapshots:
                logger.debug("Updating test snapshots for {}", self._command_id)
                _copy_test_snapshots(self.sandbox, self.sandbox_died_event)

            self.phase = "creating_report"

            logger.debug("Making final report for {}", self._command_id)
            with self.final_junit_report_lock:
                logger.debug("Locker for final report for {}", self._command_id)
                is_failed = exit_code != 0
                self.final_junit_report = self.get_junit_report(is_final=True, is_failed=is_failed)
                logger.debug("Set final junit report for {} (as failed={})", self._command_id, is_failed)

            # if IS_TESTING:
            #     time.sleep(60 * 60)

            self.phase = "killing_sandbox"

            # if the test passed, or if it failed but we're not waiting on failure, we can kill the sandbox
            if exit_code == 0 or (exit_code != 0 and not self.is_waiting_on_failure):
                self.kill_sandbox()

            self.phase = "done"
        except EnvironmentStoppedError:
            if self.exit_code is None:
                self.exit_code = 1000
            if self._stop_event.is_set():
                self.phase = "stopped_by_env_failure"
                return
            raise
        except Exception as e:
            if self.exit_code is None:
                self.exit_code = 1001
            if self._stop_event.is_set():
                self.phase = "stopped_from_exception"
                sandbox = self.sandbox
                if sandbox is not None:
                    safely_terminate_sandbox(sandbox)
                return
            self.phase = "exception"
            if not isinstance(e, (ShutdownError, GRPCError)):
                log_exception(e, "Exception in RemoteTest")
            self.sandbox_died_event.set()
            handle_sandbox_failure(self.sandbox, e, is_known_sandbox_failure=isinstance(e, GRPCError))

    def get_current_output(self) -> tuple[str, str]:
        if self.process:
            return self.process.read_stdout(), self.process.read_stderr()
        else:
            return "", ""

    def read_file(self, path: str) -> str:
        if self.failed:
            return ""
        if self.sandbox is None:
            return ""
        assert self.sandbox_died_event is not None
        return _read_file_via_sandbox(self.sandbox, path, self.sandbox_died_event)

    def poll(self) -> int | None:
        if self.process is None:
            return None
        try:
            return self.process.poll()
        except EnvironmentStoppedError:
            if self.exit_code is None:
                return 1000
            else:
                return self.exit_code

    def stop(self) -> None:
        self.kill_sandbox()
        if self.process is not None:
            self.process.abandon()

    def join(self):
        # wait for the sandbox to come online or for us to fail
        while not self._stop_event.is_set() and not self.process is None and self._sandbox_thread.is_alive():
            time.sleep(0.5)

        if self.process is not None:
            try:
                self.process.wait()
            except ProcessSetupError:
                pass
        self._stop_event.set()
        self._sandbox_thread.join()

    def kill_sandbox(self) -> None:
        self._stop_event.set()
        if self.sandbox_died_event is not None:
            self.sandbox_died_event.set()
        if self.sandbox is not None:
            try:
                self.sandbox.terminate()
            except modal.exception.SandboxTimeoutError:
                pass
            self.sandbox = None
        if self.sandbox_died_event is not None:
            self.sandbox_died_event.set()

    def get_junit_report(self, is_final: bool, is_failed: bool = False) -> ElementTree.Element:
        file_data = self.read_file(REMOTE_JUNIT_PATH)
        if file_data:
            junit_report = ElementTree.fromstring(file_data)
        else:
            duration = self.get_effective_duration()
            stdout, stderr = self.get_current_output()
            junit_report = create_junit_report_for_single_test(
                self.test_args, stdout, stderr, duration, status="failure" if is_failed or is_final else "skipped"
            )

        # add an attachment that points to the html report with the full output
        add_output_links_to_report(junit_report, self._command_id, self.commit_hash)

        # finally add the repro command if we have it
        if self.repro_command:
            add_repro_command_to_report(junit_report, self.repro_command)

        return junit_report


def write_test_names_to_sandbox(
    sandbox: modal.Sandbox, test_names: list[str], sandbox_died_event: Event, keyfile: str = "modal_ssh_key"
) -> None:
    full_write_test_list_command = " && ".join(
        f"echo '{x}' >> /user_home/workspace/tests_to_run.txt" for x in test_names
    )
    write_test_list_exit_code, write_test_list_stdout, write_test_list_stderr = run_idempotent_process_in_sandbox(
        sandbox, full_write_test_list_command, sandbox_died_event, keyfile=keyfile
    )
    assert write_test_list_exit_code == 0, (
        f"Failed to save tests to file: {write_test_list_stderr}\n{write_test_list_stdout}"
    )


def _read_file_via_sandbox(sandbox: modal.Sandbox, remote_path: str, sandbox_died_event: Event) -> str:
    random_local_path = f"/tmp/remote_test_file_{uuid4().hex}.txt"
    ssh_args = get_ssh_connection_command_as_args(sandbox)
    user_and_host = ssh_args.pop(-1)
    ssh_args_str = " ".join(ssh_args)
    rsync_args = [
        "rsync",
        "-avz",
        "-e",
        ssh_args_str,
        f"{user_and_host}:{remote_path}",
        random_local_path,
    ]
    result = run_blocking(rsync_args, shutdown_event=sandbox_died_event, is_checked=False)
    if result.returncode == 0:
        output = Path(random_local_path).read_text()
        try:
            Path(random_local_path).unlink(missing_ok=True)
        except Exception as e:
            log_exception(
                e, f"Failed to delete temporary file {random_local_path}", priority=ExceptionPriority.LOW_PRIORITY
            )
        return output
    else:
        return ""


def _no_op_on_failure(test: RemoteTest) -> str | None:
    return None


def _copy_test_snapshots(sandbox: modal.Sandbox, sandbox_died_event: Event):
    test_snapshot_dir = "sculptor/tests/integration/frontend/__snapshots__/"
    ssh_args = get_ssh_connection_command_as_args(sandbox)
    user_and_host = ssh_args.pop(-1)
    ssh_args_str = " ".join(ssh_args)
    rsync_args = [
        "rsync",
        "-avz",
        "-e",
        ssh_args_str,
        f"{user_and_host}:/user_home/workspace/{test_snapshot_dir}",
        test_snapshot_dir,
    ]
    run_blocking(rsync_args, shutdown_event=sandbox_died_event)


def snapshot_failure(test: RemoteTest) -> tuple[str, str, str]:
    # take a snapshot of the container so that we can always get back here
    start_time = time.monotonic()
    try:
        # wait just a little bit longer in case a lot of data was produced
        snapshot = test.sandbox.snapshot_filesystem(2 * 60)
        end_time = time.monotonic()
        logger.info(f"Failure snapshot took {end_time - start_time:.1f} seconds")
        repro_command = (
            f"uv run --project sculptor python sculptor/sculptor/cli/dev.py run-test-image {snapshot.object_id}"
        )
        ssh_connection_string = " ".join(
            get_ssh_connection_command_as_args(test.sandbox) + ["'cd /user_home/workspace && exec bash'"]
        )
        rsync_command = " ".join(get_code_rsync_command(test.sandbox))
    except Exception as e:
        end_time = time.monotonic()
        logger.error(f"Failed to create failure snapshot because {e}, took {end_time - start_time:.1f} seconds")
        repro_command = f"uv run --project sculptor python sculptor/sculptor/cli/dev.py run-single-test {test.modal_image.object_id} --test-names='{','.join(test.test_args)}' --command='{test.command}'"
        ssh_connection_string = ""
        rsync_command = ""
    return repro_command, rsync_command, ssh_connection_string
