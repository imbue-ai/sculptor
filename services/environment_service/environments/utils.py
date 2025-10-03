import time
from functools import wraps
from typing import Any
from typing import Callable
from typing import TypeVar

from loguru import logger

from imbue_core.async_monkey_patches import log_exception
from imbue_core.processes.local_process import run_blocking
from imbue_core.subprocess_utils import ProcessError
from sculptor.interfaces.environments.v1.base import Environment
from sculptor.interfaces.environments.v1.provider_status import DownStatus
from sculptor.interfaces.environments.v1.provider_status import OkStatus
from sculptor.interfaces.environments.v1.provider_status import ProviderStatus
from sculptor.services.environment_service.providers.docker.errors import ProviderIsDownError
from sculptor.services.environment_service.providers.docker.statuses import DockerDaemonNotRunningStatus
from sculptor.services.environment_service.providers.docker.statuses import DockerNotAvailableStatus
from sculptor.services.environment_service.providers.docker.statuses import DockerPermissionDeniedStatus

T = TypeVar("T")


def _is_environment_error_transient(environment_error: Exception) -> bool:
    return False


def check_provider_health_on_failure(
    func: Callable[..., T],
    retries_on_transient_error: int = 3,
    secs_between_retries: float = 0.5,
) -> Callable[..., T]:
    """
    Decorator for Environment methods that retries on transient errors and
    runs a provider health check after each failure.

    If the health check indicates the provider is down, it replaces the original
    exception with a ProviderError containing the health check details.
    """

    @wraps(func)
    def wrapper(self: "Environment", *args: Any, **kwargs: Any) -> T:
        last_error: Exception | None = None
        for attempt in range(retries_on_transient_error):
            try:
                return func(self, *args, **kwargs)
            except Exception as original_error:
                last_error = original_error

                # Run health check if configured
                if self._provider_health_check is not None:
                    try:
                        logger.debug("Checking provider health: {}", type(self))
                        health_status = self._provider_health_check()
                    except Exception as health_check_error:
                        log_exception(original_error, message="Provider health check failed")
                        raise health_check_error

                    if isinstance(health_status, DownStatus):
                        logger.debug("Provider is down")
                        details_msg = f" (details: {health_status.details})" if health_status.details else ""
                        raise ProviderIsDownError(
                            f"Provider is unavailable: {health_status.message}{details_msg}"
                        ) from original_error

                    logger.debug("Provider health check passed")
                if not _is_environment_error_transient(original_error):
                    raise
                time.sleep(secs_between_retries)
        if last_error is None:
            raise ValueError("Environment function did not succeed or run provider health checks")
        raise last_error

    return wrapper


def get_docker_status() -> ProviderStatus:
    """
    Get the current status of the Docker provider.

    Returns:
        ProviderStatus: The current status of the Docker provider.
    """
    try:
        run_blocking(
            command=["docker", "ps"],
            is_output_traced=False,
            timeout=15.0,
        )
        return OkStatus(message="Docker is available")
    except ProcessError as e:
        error_msg = str(e).lower()
        if "permission denied" in error_msg:
            return DockerPermissionDeniedStatus()
        elif "cannot connect" in error_msg or "daemon" in error_msg:
            return DockerDaemonNotRunningStatus()
        else:
            return DockerNotAvailableStatus(message=str(e))
