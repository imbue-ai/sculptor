"""Pytest configuration for the soak test suite.

The soak suite is **opt-in**. Without ``--run-soak`` on the command line,
every test marked ``@pytest.mark.soak`` is skipped at collection time so
the regular ``just test-integration`` run never spends minutes on it.

To run::

    just test-integration sculptor/tests/integration/soak/ --run-soak
    just test-integration-electron sculptor/tests/integration/soak/ --run-soak
"""

from typing import Generator

import pytest

from sculptor.testing.auto_update_mock import mock_electron_api as mock_electron_api  # noqa: F401
from sculptor.testing.playwright_conftest import *  # noqa: F401, F403


@pytest.fixture(autouse=True)
def always_explode_on_error() -> Generator[None, None, None]:
    """Disable the root conftest's error-logging guard for soak tests.

    Soak deliberately stresses the app — race conditions and recovered-from
    errors will produce ``logger.error`` calls (e.g. worktree cleanup races
    when a workspace is deleted with uncommitted writes). The default
    fixture treats any logged error as a teardown failure, which is the
    wrong policy here; the soak's own JSONL log captures errors for review.
    """
    yield


@pytest.fixture(scope="session")
def sculptor_launch_mode(request: pytest.FixtureRequest) -> str:
    return request.config.getoption("--sculptor-launch-mode", default="electron")


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-soak",
        action="store_true",
        default=False,
        help="Include @pytest.mark.soak tests in the run (opt-in; off by default).",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "soak: long-running soak test (opt-in via --run-soak)")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-soak"):
        return
    skip_marker = pytest.mark.skip(reason="Soak test skipped; pass --run-soak to include.")
    for item in items:
        if item.get_closest_marker("soak") is not None:
            item.add_marker(skip_marker)
