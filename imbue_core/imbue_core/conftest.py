import contextlib
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Generator

import pytest
from _pytest.junitxml import xml_key

from imbue_core.log_utils import ensure_core_log_levels_configured


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Set JUnit XML name to the full test ID for exact matching with Offload."""
    xml = item.config.stash.get(xml_key, None)
    if xml is None:
        return

    offload_root = os.environ.get("OFFLOAD_ROOT")
    if offload_root:
        fspath = str(item.path)
        rel_path = os.path.relpath(fspath, offload_root)
        nodeid_parts = item.nodeid.split("::")
        test_id = "::".join([rel_path] + nodeid_parts[1:])
    else:
        test_id = item.nodeid

    xml.node_reporter(item.nodeid).add_attribute("name", test_id)


@pytest.fixture(scope="session", autouse=True)
def setup_logging_and_secrets() -> None:
    ensure_core_log_levels_configured()


@contextlib.contextmanager
def create_temp_file(contents: str, suffix: str, root_dir: Path) -> Generator[Path, None, None]:
    with NamedTemporaryFile(mode="w", suffix=suffix, dir=root_dir, delete=False) as temp_file:
        temp_file.write(contents)
        temp_file.flush()
        yield Path(temp_file.name)
        temp_file.close()
        Path(temp_file.name).unlink()
