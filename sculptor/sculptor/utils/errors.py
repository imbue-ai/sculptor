from sqlite3 import OperationalError

from sculptor.foundation.thread_utils import ObservableThread


def is_irrecoverable_exception(exception: BaseException) -> bool:
    """
    For some exceptions, we want to crash the app immediately.

    By convention, in these cases we crash because we can't really act on the error anyway.
    """
    exception_message = str(exception)
    if isinstance(exception, OperationalError) and (
        "disk I/O error" in exception_message or "unable to open database file" in exception_message
    ):
        return True
    # Add more such cases here if needed.
    return False


def setup_irrecoverable_exception_handler() -> None:
    """Make all ObservableThreads crash the process immediately on irrecoverable exceptions."""
    ObservableThread.set_irrecoverable_exception_handler(is_irrecoverable_exception)
