import re
import subprocess
import time
from pathlib import Path

from sculptor.constants import PROXY_CACHE_PATH


def get_cache_dir_from_snapshot(snapshot) -> Path:
    """We want to create a cache file per test, not per test-file."""
    test_file = Path(snapshot.test_location.filepath)
    snapshot_dir = test_file.parent / "__snapshots__" / test_file.stem
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    cache_dir = snapshot_dir / regularize_integration_test_name(snapshot.test_location.testname)
    return cache_dir.absolute()


def regularize_integration_test_name(testname: str) -> str:
    """
    Keep only 'v1' or 'dist' from inside the [...] part of a test name,
    dropping any browser identifiers regardless of their position.
    """
    pattern = re.compile(
        r"""
        ^(?P<base>[^\[]+)\[      # base test name up to the opening bracket
        (?P<params>[^\]]+)       # everything inside [...]
        \]$                      # closing bracket
        """,
        re.VERBOSE,
    )

    match = pattern.match(testname)
    if not match:
        return testname

    params = match.group("params").split("-")
    # Keep only v1 or dist
    sut_parts = [p for p in params if p in {"v1", "dist"}]

    if not sut_parts:
        # If no v1/dist, return unchanged
        return testname

    # By your examples, there should only ever be one meaningful sut
    return f"{match.group('base')}[{sut_parts[0]}]"


def save_caches_to_snapshot_directory(local_path: Path, containers_with_tasks: tuple[tuple[str, str], ...]) -> None:
    for i, (container_id, task_id) in enumerate(containers_with_tasks):
        snapshot_filename = f"task_{i}.llm_cache_db"
        cache_path = local_path / snapshot_filename
        copy_cache_db_from_container(container_id=container_id, local_path=cache_path)


def copy_cache_db_from_container(container_id: str, local_path: Path) -> None:
    proxy_cache_dir = PROXY_CACHE_PATH
    local_path = local_path.expanduser().resolve()
    local_path.parent.mkdir(parents=True, exist_ok=True)

    # This is currently necessary since it's possible the test is done before container setup is finished for restarts
    # Remove when a frontend indicator is created
    proxy_cache_exists = False
    start = time.time()
    while time.time() - start < 60.0:
        if (
            subprocess.run(["docker", "exec", "-u", "root", container_id, "test", "-f", proxy_cache_dir]).returncode
            == 0
        ):
            proxy_cache_exists = True
            break
        time.sleep(1.0)

    if not proxy_cache_exists:
        raise FileNotFoundError("Could not find proxy cache in container")

    subprocess.run(
        ["docker", "cp", f"{container_id}:{proxy_cache_dir}", str(local_path)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
