import time

import modal
from loguru import logger
from tenacity import RetryCallState
from tenacity import retry
from tenacity import retry_all
from tenacity import retry_if_exception_type
from tenacity import stop_after_attempt
from tenacity import wait_random_exponential

from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.git import get_git_repo_root
from sculptor.interfaces.environments.v1.base import ModalEnvironmentConfig
from sculptor.interfaces.environments.v1.base import ModalImage
from sculptor.interfaces.environments.v1.constants import CONTAINER_SSH_PORT
from sculptor.primitives.ids import ModalSandboxObjectID
from sculptor.services.environment_service.environments.modal_environment import ModalEnvironment
from sculptor.services.environment_service.environments.modal_environment import remove_modal_sandbox
from sculptor.services.environment_service.environments.modal_environment import stop_modal_sandbox
from sculptor.services.environment_service.providers.modal.app_context import ModalAppWithOutputBuffer
from sculptor.services.environment_service.providers.modal.app_context import use_modal_app
from sculptor.services.environment_service.providers.modal.errors import ModalExecutorTimeoutError


def _log_sandbox_retry(retry_state: RetryCallState) -> None:
    """This function is used to log the retry a test running on a sandbox."""
    fn_name = retry_state.fn.__name__ if retry_state.fn is not None else "unknown"
    sleep_time = retry_state.next_action.sleep if retry_state.next_action is not None else 0
    outcome = retry_state.outcome

    if outcome is not None:
        exception = outcome.exception()
        error_message = type(exception).__name__ + ": " + str(exception)
    else:
        error_message = "unknown"

    logger.warning(
        f"Retrying {fn_name} in {sleep_time:.2f} seconds, attempt {retry_state.attempt_number} due to sandbox failure: {error_message}"
    )


retry_sandbox_creation = retry(
    stop=stop_after_attempt(3),
    wait=wait_random_exponential(min=1.0, max=10.0, exp_base=3),
    retry=retry_all(retry_if_exception_type((ModalExecutorTimeoutError,))),
    before_sleep=_log_sandbox_retry,
)


def build_modal_environment(
    modal_image: ModalImage,
    project_id: ProjectID,
    config: ModalEnvironmentConfig = ModalEnvironmentConfig(),
    environment_prefix: str = "",
) -> ModalEnvironment:
    with use_modal_app(modal_image.app_name, is_detached=True) as app:
        image = modal.Image.from_id(modal_image.image_id)
        sandbox = build_sandbox_in_app(app, image, config=config)
        logger.info("Created sandbox with id: {}", sandbox.object_id)
        return ModalEnvironment(
            config=config,
            project_id=project_id,
            environment_id=ModalSandboxObjectID(sandbox.object_id),
            app_name=modal_image.app_name,
        )


# FIXME: this needs to understand when we ran a copy layer, and from that, save the result to the database
@retry_sandbox_creation
def build_sandbox_in_app(
    app: ModalAppWithOutputBuffer,
    image: modal.Image,
    config: ModalEnvironmentConfig,
    copy_layer_cache_keys: list[str] | None = None,
    should_run_ssh_server: bool = True,
) -> modal.Sandbox:
    # FIXME: make sure we've set unencrypted_ports and exposed_ports
    logger.info("Creating new modal sandbox")
    try:
        start_time = time.monotonic()
        modal_sandbox = modal.Sandbox.create(
            app=app,
            image=image,
            timeout=config.timeout,
            workdir=config.cwd,
            gpu=config.gpu,
            cpu=config.cpu,
            memory=config.memory,
            encrypted_ports=config.exposed_ports or [],
            unencrypted_ports=config.unencrypted_ports or [],
            region=config.region,
            experimental_options={"enable_docker": True},
        )
        logger.info("Started modal sandbox in {:.2f}s.", time.monotonic() - start_time)
    except modal.exception.TimeoutError as e:
        logger.debug("Retrying on timeout error {} while trying to make a Modal Sandbox", e)
        raise ModalExecutorTimeoutError("While creating sandbox") from e
    # FIXME: handle other errors

    logger.trace("Successfully created modal sandbox from config")
    logger.info("Sandbox ID: {}", modal_sandbox.object_id)
    if should_run_ssh_server:
        try:
            _run_ssh_server_in_sandbox(modal_sandbox)
        except modal.exception.SandboxTimeoutError as e:
            logger.debug("Retrying on timeout error {} while trying to get the tunnels for the ssh server", e)
            raise ModalExecutorTimeoutError("While getting tunnels") from e
    return modal_sandbox


def _run_ssh_server_in_sandbox(sandbox: modal.Sandbox) -> tuple[str, int, str]:
    logger.info("Running ssh server in sandbox")
    authorized_keys_contents = _get_debugging_ssh_public_key_contents()

    sandbox.exec("mkdir", "-p", "/root/.ssh")

    with sandbox.open("/root/.ssh/authorized_keys", "wb") as f:
        f.write(authorized_keys_contents)

    # -D : don't detach
    # -e : print errors to stdout
    ssh_process = sandbox.exec("/usr/sbin/sshd", "-D", "-e")

    # TODO: idk if this call is necessary? we're not using the return value
    return get_ssh_info_from_modal_sandbox(sandbox)


def get_ssh_info_from_modal_sandbox(sandbox: modal.Sandbox) -> tuple[str, int, str]:
    tunnels = sandbox.tunnels()
    ssh_tunnel = tunnels[CONTAINER_SSH_PORT]
    ssh_host, ssh_port = ssh_tunnel.tcp_socket
    return ssh_host, ssh_port, "root"


def _get_debugging_ssh_public_key_contents() -> bytes:
    debugging_ssh_public_key_path = get_git_repo_root() / "science" / "secrets" / "modal" / "modal.ed25519.pub"
    return debugging_ssh_public_key_path.read_bytes()


def destroy_outdated_modal_sandboxes(environment_prefix: str) -> None:
    _handle_outdated_modal_sandboxes(environment_prefix=environment_prefix, is_stopped=False)


def stop_outdated_modal_sandboxes(environment_prefix: str) -> None:
    _handle_outdated_modal_sandboxes(environment_prefix=environment_prefix, is_stopped=True)


# FIXME: actually implement in order to support modal sandboxes
def _get_sandboxes_from_environment_prefix(environment_prefix: str) -> list[ModalSandboxObjectID]:
    return []


def _handle_outdated_modal_sandboxes(environment_prefix: str, is_stopped: bool) -> None:
    for sandbox_id in _get_sandboxes_from_environment_prefix(environment_prefix):
        if is_stopped:
            stop_modal_sandbox(sandbox_id)
        else:
            remove_modal_sandbox(sandbox_id)
