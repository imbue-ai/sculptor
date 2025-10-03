import os
from functools import lru_cache


# by calling this really early in the life of the program, you can be more likely to get the actual parent
@lru_cache(maxsize=1)
def get_original_parent_pid():
    return os.getppid()
