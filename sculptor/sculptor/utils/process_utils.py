import os
from functools import lru_cache


@lru_cache(maxsize=1)
def get_original_parent_pid() -> int:
    """Return this process's parent PID, captured on the first call.

    Call this early in the program's life to be more likely to capture the
    actual parent before the process is reparented.
    """
    return os.getppid()
