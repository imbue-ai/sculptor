import functools
import os
import platform
import sys
import uuid
from pathlib import Path


def is_on_osx() -> bool:
    return platform.system().lower() == "darwin"


def is_running_within_a_pytest_tree() -> bool:
    """
    This is true if this, or any parent process, is running under pytest.

    This is usually what you want to check
    (eg, this will be true even if you are a separately launched integration server process)
    """
    return "PYTEST_CURRENT_TEST" in os.environ


def is_live_debugging() -> bool:
    """
    Returns True if the current process is being debugged, for example by PyCharm or another IDE.
    """
    # sys.gettrace() is not None would also be true when measuring coverage and in other cases;
    # checking breakpointhook is the narrower signal that is only true when debugging (e.g. in PyCharm).
    return sys.breakpointhook.__module__ != "sys"


@functools.lru_cache(maxsize=1)
def get_filesystem_root() -> Path:
    env_value = os.getenv("SCIENCE_FILESYSTEM_ROOT")
    if not env_value:
        if is_on_osx():
            return Path("/tmp/science")
        else:
            # When on the physical cluster (and possibly other core clusters), this path is mounted to a unique per-container file path.
            # Anything produced at runtime >10mb should likely go here, as well as anything you might want to dig up for later debugging.
            # The hosts clean up the paths from dead containers periodically, but large data processing jobs should still clean up after themselves.
            return Path("/mnt/private")
    return Path(env_value)


@functools.lru_cache(maxsize=1)
def get_temp_dir() -> Path:
    temp_dir = get_filesystem_root() / "tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


def generate_id() -> str:
    return uuid.uuid4().hex


_TRUNCATION_SUFFIX = "..."


def truncate_string(s: str, max_length: int) -> str:
    if len(s) <= max_length:
        return s
    return s[: max_length - len(_TRUNCATION_SUFFIX)] + _TRUNCATION_SUFFIX


def parse_bool_environment_variable(var_name: str) -> bool:
    env_var = os.environ.get(var_name, "0").lower()

    if env_var not in ("0", "1", "true", "false"):
        raise ValueError(
            f"{var_name} environment variable must be '0', '1', 'true', or 'false'. Current value: '{env_var}'"
        )

    return env_var in ("1", "true")
