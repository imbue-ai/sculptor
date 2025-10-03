import time
from pathlib import Path
from threading import Event
from xml.etree import ElementTree

import modal
from grpclib import GRPCError
from loguru import logger
from modal import Sandbox
from modal.exception import ClientClosed

from imbue_core.async_monkey_patches import log_exception
from imbue_core.constants import ExceptionPriority
from imbue_core.processes.data_types import SSHConnectionData
from imbue_core.processes.errors import EnvironmentStoppedError
from imbue_core.processes.local_process import run_blocking
from imbue_core.processes.remote_process import RemoteRunningProcess
from imbue_core.processes.remote_process import get_full_ssh_command_args
from imbue_core.processes.remote_process import get_ssh_connection_details
from imbue_core.processes.remote_process import run_idempotent_remote_command_until_complete
from imbue_core.processes.remote_process import run_remote_command_in_background_with_lazy_output
from sculptor.cli.dev_commands.run_tests.reporting import add_output_links_to_report
from sculptor.cli.dev_commands.run_tests.reporting import add_repro_command_to_report
from sculptor.interfaces.environments.v1.base import ModalEnvironmentConfig
from sculptor.interfaces.environments.v1.constants import CONTAINER_SSH_PORT
from sculptor.services.environment_service.providers.modal.app_context import ModalAppWithOutputBuffer
from sculptor.services.environment_service.providers.modal.environment_utils import get_ssh_info_from_modal_sandbox


def build_sandbox_in_app(
    app: ModalAppWithOutputBuffer,
    image: modal.Image,
    config: ModalEnvironmentConfig,
    is_docker_enabled: bool = True,
    is_networking_enabled: bool = True,
    volumes: dict[str, modal.Volume] | None = None,
    keyfile: str = "modal_ssh_key",
) -> modal.Sandbox:
    logger.info("Creating new modal sandbox")
    assert config.unencrypted_ports and CONTAINER_SSH_PORT in config.unencrypted_ports, (
        "SSH port must be included in unencrypted_ports"
    )
    start_time = time.monotonic()
    end_time = start_time + config.timeout
    modal_sandbox = modal.Sandbox.create(
        # -D : don't detach
        *["/usr/sbin/sshd", "-D"],
        app=app,
        image=image,
        timeout=config.timeout,
        workdir=config.cwd,
        gpu=config.gpu,
        cpu=config.cpu,
        memory=config.memory,
        encrypted_ports=config.exposed_ports or [],
        unencrypted_ports=config.unencrypted_ports,
        region=config.region,
        volumes=volumes or {},
        experimental_options={"enable_docker": True} if is_docker_enabled else None,
        cidr_allowlist=None
        if is_networking_enabled
        else [
            "127.0.0.0/8",  # Loopback (localhost)
            "10.0.0.0/8",  # Private Class A
            "172.16.0.0/12",  # Private Class B
            "192.168.0.0/16",  # Private Class C
            "169.254.0.0/16",  # Link-local
            "::1/128",  # IPv6 loopback
            "fc00::/7",  # IPv6 unique local addresses
            "fe80::/10",  # IPv6 link-local
        ],
    )
    logger.info(
        "Modal started sandbox {} in {:.2f}s, waiting for it to come online...",
        modal_sandbox.object_id,
        time.monotonic() - start_time,
    )

    # do this before returning, otherwise commands can fail kind of randomly
    while not _run_sandbox_health_check(modal_sandbox, keyfile=keyfile):
        time.sleep(1.0)
        if time.monotonic() > end_time:
            try:
                modal_sandbox.terminate()
            # FIXME: sigh, this is an annoying way to accidentally end up with a running remote sandbox
            #  the only real way around this is to have the sandboxes kill themselves with a heartbeat pattern
            except Exception as e:
                logger.debug("Failed to terminate sandbox after timeout: {}", e)
            raise TimeoutError("Timed out waiting for sandbox to become healthy")

    return modal_sandbox


def _run_sandbox_health_check(modal_sandbox: Sandbox, keyfile: str = "modal_ssh_key") -> bool:
    host, port, username = get_ssh_info_from_modal_sandbox(modal_sandbox)
    connection = SSHConnectionData(host=host, port=port, user=username, keyfile=Path(keyfile))
    ssh_connection_details = get_ssh_connection_details(connection)
    full_command = get_full_ssh_command_args("echo yes I am online", ssh_connection_details)
    result = run_blocking(full_command, is_checked=False)
    return result.returncode == 0


def launch_idempotent_process_in_sandbox(
    sandbox: modal.Sandbox,
    command: list[str] | str,
    sandbox_died_event: Event,
    command_id: str | None = None,
    is_tty: bool = False,
    keyfile: str = "modal_ssh_key",
) -> RemoteRunningProcess:
    host, port, username = get_ssh_info_from_modal_sandbox(sandbox)
    connection = SSHConnectionData(host=host, port=port, user=username, keyfile=Path(keyfile))
    logger.debug(f"Running command on {connection} via SSH: {command}")
    return run_remote_command_in_background_with_lazy_output(
        command, connection, environment_shutdown_event=sandbox_died_event, command_id=command_id, is_tty=is_tty
    )


class SandboxDeathEvent:
    """Has the read-only interface of an Event, but is set if any child event is set."""

    def __init__(self, sandbox: modal.Sandbox, event: Event) -> None:
        self.sandbox = sandbox
        self.event = event

    def set(self):
        self.event.set()

    def is_set(self) -> bool:
        try:
            exit_code = self.sandbox.poll()
        except ClientClosed as e:
            # if the client is closed, the sandbox is definitely dead (to us)
            logger.trace("Sandbox client closed: {}", e)
            exit_code = -3
        except Exception as e:
            log_exception(e, "Failed to poll sandbox", priority=ExceptionPriority.LOW_PRIORITY)
            # guess you're dead
            exit_code = -2
        if exit_code is not None:
            self.event.set()
        return self.event.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        start = time.monotonic()
        while timeout is None or time.monotonic() - start < timeout:
            if self.is_set():
                return True
            time.sleep(0.01)
        return False


def handle_sandbox_failure(sandbox: modal.Sandbox | None, e: Exception, is_known_sandbox_failure: bool):
    if is_known_sandbox_failure:
        raise EnvironmentStoppedError("Sandbox failure") from e

    if sandbox is None:
        raise EnvironmentStoppedError("Didn't even create the sandbox") from e
    # otherwise check to see if the sandbox is still alive
    try:
        is_online = _run_sandbox_health_check(sandbox)
    except Exception as e2:
        raise EnvironmentStoppedError(f"Failed to communicate with sandbox: {e2}") from e
    if not is_online:
        raise EnvironmentStoppedError("Sandbox is not online") from e

    safely_terminate_sandbox(sandbox)
    raise


def safely_terminate_sandbox(sandbox: modal.Sandbox | None):
    # FIXME: hmmm... not so sure about this, but hopefully it's gone, don't really want to block...
    # and I guess we might as well shut down the sandbox?
    try:
        sandbox.terminate()
    except (GRPCError, modal.Error) as e:
        logger.info("Failed to terminate sandbox after failure: {}", e)
    except Exception as e2:
        log_exception(e2, "Failed to terminate sandbox after failure", priority=ExceptionPriority.LOW_PRIORITY)


def run_idempotent_process_in_sandbox(
    sandbox: modal.Sandbox,
    command: list[str] | str,
    sandbox_died_event: Event,
    is_logged: bool = True,
    keyfile: str = "modal_ssh_key",
) -> tuple[int, str, str]:
    host, port, username = get_ssh_info_from_modal_sandbox(sandbox)
    connection = SSHConnectionData(host=host, port=port, user=username, keyfile=Path(keyfile))
    if is_logged:
        logger.debug(f"Running command on {connection} via SSH: {command}")
    return run_idempotent_remote_command_until_complete(
        command=command, ssh_connection=connection, stop_event=sandbox_died_event
    )


def main():
    # ssh -T -i modal_ssh_key -p 39239 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no -o LogLevel=ERROR root@ "/bin/bash -l -c 'cat /tmp/junit.xml'"
    host, port, username = "r451.modal.host", 39239, "root"
    connection = SSHConnectionData(host=host, port=port, user=username, keyfile=Path("modal_ssh_key"))
    exit_code, file_data, stderr = run_idempotent_remote_command_until_complete(
        command=["cat", "/tmp/junit.xml"], ssh_connection=connection, stop_event=Event()
    )
    junit_report = ElementTree.fromstring(file_data)

    # add an attachment that points to the html report with the full output
    add_output_links_to_report(junit_report, "foobar", "something")

    # finally add the repro command if we have it
    add_repro_command_to_report(junit_report, "blargle")
    return len(file_data)


if __name__ == "__main__":
    print(main())
