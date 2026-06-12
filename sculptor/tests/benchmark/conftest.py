import csv
from pathlib import Path

import pytest
from playwright.sync_api import expect
from tabulate import tabulate


# NOTE: This is copied from and duplicative of tests/integration/frontend/conftest.py
# This will be refactored in the test rewrite.
@pytest.fixture(autouse=True)
def configure_expect_timeout(is_updating_snapshots_: bool) -> None:
    if is_updating_snapshots_:
        expect.set_options(timeout=5 * 60 * 1000)
    else:
        expect.set_options(timeout=4 * 60 * 1000)


def _find_perf_results_csv(config) -> Path | None:
    default_dir = Path(config.rootpath) / "performance_results"
    candidates = list(default_dir.glob("*.csv"))
    if candidates:
        # Prefer results.csv if present, else first csv
        for p in candidates:
            if p.name == "results.csv":
                return p
        return candidates[0]
    return None


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Let us write out a summary of the performance results."""
    csv_path = _find_perf_results_csv(config)
    if not csv_path or not csv_path.exists():
        terminalreporter.write_line("[perf] No performance results CSV found.")
        return

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        terminalreporter.write_line("[perf] results CSV is empty.")
        return

    # Print a small, stable subset of columns if present
    cols = [c for c in ["name", "avg_time", "sem", "repeats", "min_value", "max_value"] if c in rows[0]]

    table_rows = [[r.get(c, "") for c in cols] for r in rows]

    terminalreporter.write_sep("=", f"PerformanceTotal results ({csv_path})")
    terminalreporter.write_line(tabulate(table_rows, headers=cols, tablefmt="github"))
