import asyncio
import traceback
from typing import Any

from sculptor.foundation.constants import ExceptionPriority

# This is the name of the attribute we set on our exceptions to ensure they are logged (esp. to Sentry) at most once.
EXCEPTION_LOGGED_FLAG = "_was_logged_by_log_exception"


def safe_cancel(task: asyncio.Task, msg: str | None = None) -> None:
    """
    Cancels a task in a way that preserves information about who canceled it.

    Without using this, it is hard to figure out why your function is being canceled --
    you just get a CancelledError with no traceback.

    We try to ensure that *all* of our tasks are canceled in this way, which makes debugging much easier.

    Note that cancellation just enqueues a cancellation; it does not wait for the task to actually be canceled.

    Note also that cancellation is never guaranteed -- all it does is raise a CancelledError in the task.
    This is why it is so important to never swallow those errors!
    """
    message = f"Task canceled by: \n {''.join(traceback.format_stack()[:-1])}"
    if msg:
        message += f"\nOriginal message: {msg}"

    task.cancel(message)


def pre_filter_exception(exc: BaseException, message: str | None = None) -> bool:
    # deferred import, will have been imported anyway by this point
    from loguru import logger

    if getattr(exc, EXCEPTION_LOGGED_FLAG, False):
        logger.info("Skipping duplicate log of exception {} with message {!r}", exc, message)
        return True
    try:
        setattr(exc, EXCEPTION_LOGGED_FLAG, True)
    except AttributeError:
        logger.info("Unable to guarantee that {} will not be logged again", exc)
    return False


def inject_exception_and_log(
    exc: BaseException, message: str, priority: ExceptionPriority | None = None, *args: Any, **kwargs: Any
) -> None:
    # deferred import, will have been imported anyway by this point
    from loguru import logger

    # inject received exception stack trace into logger error message
    # pyrefly: ignore [missing-attribute]
    options = (exc,) + logger._options[1:]
    if priority is not None:
        level = priority.value
    else:
        level = "ERROR"
    # pyrefly: ignore [missing-attribute]
    logger._log(level, False, options, message, args, kwargs)


def log_exception(
    exc: BaseException,
    message: str,
    priority: ExceptionPriority | None = None,
    *args: Any,
    **kwargs: Any,
) -> None:
    """`loguru.exception()` takes only a message, and grabs the current exception from sys.exc_info().

    This is a more explicit alternative that takes the exception as an argument.
    """
    should_skip = pre_filter_exception(exc, message)
    if should_skip:
        return None

    traceback_str = "".join(traceback.format_stack())
    message = (
        f"{message}\n\nlog_exception CALL SITE TRACEBACK:\n\n{traceback_str}\nORIGINAL EXCEPTION TRACEBACK FOLLOWS:\n"
    )

    # inject received exception stack trace into logger error message
    inject_exception_and_log(exc, message, priority, *args, **kwargs)
