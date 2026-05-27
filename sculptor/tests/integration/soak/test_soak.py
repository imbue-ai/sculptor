"""Long-running soak test driven by a random walk over UI operations.

Opt-in: pass ``--run-soak`` on the command line. Defaults to a 5-minute run.
Configurable via env vars:

* ``SCULPTOR_SOAK_DURATION_SECONDS`` — wall-clock budget (default ``300``).
* ``SCULPTOR_SOAK_SEED`` — RNG seed for reproducibility (default: time-based).
* ``SCULPTOR_SOAK_SCREENSHOT_ON_SOFT_FAIL`` — ``0`` to disable per-failure
  screenshots (default ``1``).
* ``SCULPTOR_SOAK_MAX_SOFT_FAILURES`` — when set, fail the test if the run
  records more soft failures than this. Unset means soft failures never
  fail the test, only the JSONL log.

Runs against the active ``--sculptor-launch-mode`` like any other Playwright
integration test, so the same test exercises browser, electron, and packaged
modes without per-mode code paths.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import pytest

from sculptor.testing.sculptor_instance import SculptorInstance
from tests.integration.soak.framework import SoakRunner
from tests.integration.soak.operations import DEFAULT_GLOBAL_INVARIANTS
from tests.integration.soak.operations import DEFAULT_OPERATIONS
from tests.integration.soak.operations import DEFAULT_RECOVERIES

logger = logging.getLogger(__name__)


@pytest.mark.soak
def test_soak(
    sculptor_instance_: SculptorInstance,
    tmp_path: Path,
    record_property,
) -> None:
    duration = float(os.environ.get("SCULPTOR_SOAK_DURATION_SECONDS", "300"))
    seed = int(os.environ.get("SCULPTOR_SOAK_SEED", str(int(time.time()))))
    take_screenshots = os.environ.get("SCULPTOR_SOAK_SCREENSHOT_ON_SOFT_FAIL", "1") != "0"
    max_soft_failures_env = os.environ.get("SCULPTOR_SOAK_MAX_SOFT_FAILURES")
    max_soft_failures = int(max_soft_failures_env) if max_soft_failures_env else None

    log_path = tmp_path / "soak.jsonl"
    screenshot_dir = (tmp_path / "soak-screenshots") if take_screenshots else None
    record_property("soak_log_path", str(log_path))
    if screenshot_dir is not None:
        record_property("soak_screenshot_dir", str(screenshot_dir))

    runner = SoakRunner(
        page=sculptor_instance_.page,
        operations=DEFAULT_OPERATIONS,
        recoveries=DEFAULT_RECOVERIES,
        global_invariants=DEFAULT_GLOBAL_INVARIANTS,
        duration_seconds=duration,
        seed=seed,
        log_path=log_path,
        screenshot_dir=screenshot_dir,
    )

    # Tracing on the shared instance is managed by pytest-playwright's
    # ``_artifacts_recorder`` (wired up in sculptor.testing.resources). Pass
    # ``--tracing=on`` on the command line to always retain the trace; the
    # ``--tracing=retain-on-failure`` default only saves it when the test
    # fails. The runner's ``tracing.group()`` annotations land in that trace.
    logger.info("Soak starting: duration=%.1fs seed=%d log=%s", duration, seed, log_path)
    stats = runner.run()
    logger.info(
        "Soak finished: iterations=%d ops=%s soft_failures=%d recoveries=%d",
        stats.iterations,
        stats.operations_run,
        len(stats.soft_failures),
        stats.recoveries,
    )

    record_property("soak_iterations", str(stats.iterations))
    record_property("soak_soft_failures", str(len(stats.soft_failures)))
    record_property("soak_recoveries", str(stats.recoveries))

    if max_soft_failures is not None and len(stats.soft_failures) > max_soft_failures:
        pytest.fail(
            f"Soak recorded {len(stats.soft_failures)} soft failures (budget: {max_soft_failures}). See {log_path}."
        )
