"""Shared test fixtures for sculpt CLI tests."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from _pytest.junitxml import xml_key


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


@pytest.fixture(autouse=True)
def unset_sculpt_env_vars() -> Iterator[None]:
    """Unset SCULPT_ env vars to ensure tests use defaults."""
    env_vars = ["SCULPT_API_PORT", "SCULPT_WORKSPACE_ID", "SCULPT_AGENT_ID", "SCULPT_PROJECT_ID"]
    old_values = {key: os.environ.pop(key, None) for key in env_vars}
    yield
    for key, value in old_values.items():
        if value is not None:
            os.environ[key] = value


@pytest.fixture(autouse=True)
def isolate_cli_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the CLI's local state (e.g. the MRU harness) at a temp dir.

    Keeps tests from reading or writing the real ``~/.sculpt`` state file.
    """
    monkeypatch.setenv("SCULPT_STATE_DIR", str(tmp_path / "sculpt-state"))
