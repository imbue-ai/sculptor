from loguru import logger
from tenacity import RetryCallState
from tenacity import retry
from tenacity import retry_all
from tenacity import retry_if_exception_type
from tenacity import stop_after_attempt
from tenacity import wait_random_exponential

from imbue_core.processes.errors import EnvironmentStoppedError


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


retry_sandbox_command = retry(
    stop=stop_after_attempt(3),
    wait=wait_random_exponential(min=20.0, max=6, exp_base=3),
    retry=retry_all(retry_if_exception_type((EnvironmentStoppedError,))),
    before_sleep=_log_sandbox_retry,
)
