import os
from collections.abc import Generator
from pathlib import Path

import pytest
from loguru import logger
from pytest import Session

from sculptor.config.settings import SculptorSettings
from sculptor.config.settings import TEST_LOG_PATH
from sculptor.config.settings import TestingConfig
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.fixtures import initial_commit_repo
from sculptor.foundation.git import get_repo_base_path
from sculptor.testing.timing_report import close_timeline
from sculptor.testing.timing_report import print_phase_timing_table
from sculptor.testing.timing_report import record_phase_duration
from sculptor.testing.timing_report import write_timeline_event

_IMPORTED_FIXTURES = (initial_commit_repo,)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> Generator[None, pytest.TestReport, None]:  # noqa: E501
    """Record per-phase timing on every test report."""
    outcome = yield
    result = outcome.get_result()
    record_phase_duration(result)
    write_timeline_event(result)


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    """Print a per-test timing breakdown (setup / call / teardown) at session end.

    This hook lives in the root conftest so the xdist controller always loads
    it, even when the test path is ``tests/integration/`` (sub-directory
    conftest files are only loaded on workers, not the controller).
    """
    print_phase_timing_table(terminalreporter)


def pytest_sessionstart(session: Session) -> None:
    """This function runs once per session in the controller node once execution, and then once again on every worker
    node.
    """
    if not hasattr(session.config, "workerinput"):
        with ConcurrencyGroup(name="setup_once") as concurrency_group:
            setup_once(session, concurrency_group)


def pytest_sessionfinish(session: Session) -> None:
    """This function runs once per xdist session on the controller node and once on every worker."""
    close_timeline()
    if not hasattr(session.config, "workerinput"):
        teardown_once(session)


def setup_once(session: Session, concurrency_group: ConcurrencyGroup) -> None:  # noqa: ARG001
    """This code is guaranteed to run only once on the worker node, prior to any xdist distribution."""
    logger.info("Running setup_once")
    logger.info("Finished setup_once.")


def teardown_once(session: Session) -> None:
    """This code is guaranteed to run only once on the worker node, after all tests have been executed."""
    # This is a no-op now.


@pytest.fixture
def test_settings(database_url: str) -> SculptorSettings:
    project_path: str | Path | None = os.getenv("PROJECT_PATH")
    if not project_path:
        project_path = get_repo_base_path()
    logger.info("Using project path: {}", project_path)
    settings = SculptorSettings(
        DATABASE_URL=database_url,
        LOG_PATH=str(TEST_LOG_PATH),
        LOG_LEVEL="TRACE",
        TESTING=TestingConfig(),
    )
    return settings
