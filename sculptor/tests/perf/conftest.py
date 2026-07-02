"""Pytest configuration for performance scenario tests.

These tests share the Playwright fixtures with the integration suite but
live in their own directory because they have a different success
criterion (record metrics, don't assert thresholds — yet) and a different
typical invocation (``just test-integration sculptor/tests/perf/``).
"""

from collections.abc import Generator

import pytest

from sculptor.testing.auto_update_mock import mock_electron_api as mock_electron_api  # noqa: F401
from sculptor.testing.perf.collector import MeasurementRecorder
from sculptor.testing.perf.collector import resolve_output_path
from sculptor.testing.playwright_conftest import *  # noqa: F401, F403
from sculptor.testing.playwright_utils import full_spa_reload
from sculptor.testing.sculptor_instance import SculptorInstance


@pytest.fixture(scope="session")
def sculptor_launch_mode(request: pytest.FixtureRequest) -> str:
    """Browser-mode by default — same as the frontend integration suite.

    Run with ``--sculptor-launch-mode=browser`` (the default) for plain
    Chromium; perf measurements rely on the same shared context.
    """
    return request.config.getoption("--sculptor-launch-mode", default="browser")


@pytest.fixture
def perf_recorder(
    sculptor_instance_: SculptorInstance,
    request: pytest.FixtureRequest,
) -> Generator[MeasurementRecorder, None, None]:
    """Provide a MeasurementRecorder wired to the shared instance's page.

    On setup: installs the perf init script and reloads the SPA so the
    React DevTools hook is in place before React boots, then verifies the
    hook actually picked up a renderer.

    On teardown: clears the localStorage gate (so the next test starts
    without perf collection unless it requests this fixture), and flushes
    recorded measurements to the JSONL output file.
    """
    recorder = MeasurementRecorder(
        page=sculptor_instance_.page,
        output_path=resolve_output_path(),
        test_nodeid=request.node.nodeid,
    )
    recorder.enable()
    # Hard reload to let the init script run before React boots.
    full_spa_reload(sculptor_instance_.page)
    recorder.assert_hook_wired()
    try:
        yield recorder
    finally:
        recorder.disable()
        recorder.flush()
