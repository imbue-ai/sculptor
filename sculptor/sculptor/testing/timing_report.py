"""Per-test phase timing: recording and reporting.

Both hooks (``record_phase_duration`` and ``print_phase_timing_table``) are
wired up in the root ``tests/conftest.py`` so they run for every test suite
and are visible to the xdist controller.
"""

import os
import time

import pytest

from sculptor.foundation.pydantic_serialization import FrozenModel


class _TimelineEvent(FrozenModel):
    """One JSONL timeline record for a single test phase."""

    ts: float
    pid: int
    worker: str
    nodeid: str
    phase: str
    outcome: str
    duration: float


def record_phase_duration(report: pytest.TestReport) -> None:
    """Append ``duration_{phase}`` to *report.user_properties*.

    This makes per-phase durations appear in JUnit XML and available
    for the terminal summary table.
    """
    duration_s = round(report.duration, 2)
    report.user_properties.append((f"duration_{report.when}", duration_s))


# JSONL timeline — one line per test phase with absolute timestamps, worker
# ID and PID so that CPU profiling data (pidstat) can be cross-referenced
# with individual test execution windows.

_TIMELINE_PATH = os.environ.get("TEST_TIMELINE_PATH")
_timeline_file = None  # lazily opened on first write


def write_timeline_event(report: pytest.TestReport) -> None:
    """Append a JSONL line for this test phase to the timeline log."""
    global _timeline_file
    if not _TIMELINE_PATH:
        return

    if _timeline_file is None:
        _timeline_file = open(_TIMELINE_PATH, "a")  # noqa: SIM115

    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "controller")
    event = _TimelineEvent(
        ts=time.time(),
        pid=os.getpid(),
        worker=worker_id,
        nodeid=report.nodeid,
        phase=report.when,
        outcome=report.outcome,
        duration=round(report.duration, 2),
    )
    _timeline_file.write(event.model_dump_json() + "\n")
    _timeline_file.flush()


def close_timeline() -> None:
    """Flush and close the timeline file if open."""
    global _timeline_file
    if _timeline_file is not None:
        _timeline_file.close()
        _timeline_file = None


def print_phase_timing_table(terminalreporter: pytest.TerminalReporter) -> None:
    """Print a per-test timing breakdown (setup / call / teardown)."""
    # Collect reports from ALL stat categories — passing setup/teardown reports
    # go to stats[""] (empty string key), not "passed", so iterate everything.
    all_reports: list[pytest.TestReport] = []
    for reports_list in terminalreporter.stats.values():
        for report in reports_list:
            if isinstance(report, pytest.TestReport):
                all_reports.append(report)

    # Build a map of nodeid -> {phase: duration}.
    # Each nodeid may appear multiple times (once per phase).
    timing: dict[str, dict[str, float]] = {}
    for report in all_reports:
        entry = timing.setdefault(report.nodeid, {})
        entry[report.when] = round(report.duration, 2)

    if not timing:
        return

    terminalreporter.section("Phase timing breakdown")
    header = f"{'Test':<80s} {'Setup':>8s} {'Call':>8s} {'Teardown':>8s} {'Total':>8s}"
    terminalreporter.line(header)
    terminalreporter.line("-" * len(header))

    total_setup = 0.0
    total_call = 0.0
    total_teardown = 0.0
    for nodeid, phases in sorted(timing.items()):
        setup = phases.get("setup", 0.0)
        call = phases.get("call", 0.0)
        teardown = phases.get("teardown", 0.0)
        total = round(setup + call + teardown, 2)
        total_setup += setup
        total_call += call
        total_teardown += teardown
        # Truncate long test names from the left to fit the column.
        short_name = nodeid if len(nodeid) <= 78 else "…" + nodeid[-77:]
        terminalreporter.line(f"{short_name:<80s} {setup:>7.2f}s {call:>7.2f}s {teardown:>7.2f}s {total:>7.2f}s")

    terminalreporter.line("-" * len(header))
    grand_total = round(total_setup + total_call + total_teardown, 2)
    terminalreporter.line(
        f"{'TOTAL':<80s} {total_setup:>7.2f}s {total_call:>7.2f}s {total_teardown:>7.2f}s {grand_total:>7.2f}s"
    )
