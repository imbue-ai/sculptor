#!/usr/bin/env python3
"""Print failed and flaky test names from offload's JUnit XML output.

Offload's job-log summary reports counts only ("Failed: 4, Flaky: 3"),
not test names. This script parses the JUnit artifact and prints the
names so they're visible at the end of the CI job log without having
to download artifacts.

Classification (offload runs each test multiple times under retry_count):
  - failed: every run for that test name had a <failure>
  - flaky:  at least one run failed AND at least one run passed

Always exits 0 so it can run from `after_script` without overriding the
job's real exit code.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

DEFAULT_JUNIT_PATH = Path("test-results/junit-integration.xml")
_BANNER_WIDTH = 72


def main(argv: Sequence[str]) -> int:
    junit_path = Path(argv[1]) if len(argv) > 1 else DEFAULT_JUNIT_PATH

    try:
        root = ET.parse(junit_path).getroot()
    except FileNotFoundError:
        print(f"[offload-summary] No JUnit at {junit_path} — offload may have failed before writing results.")
        return 0
    except ET.ParseError as exc:
        print(f"[offload-summary] Could not parse {junit_path}: {exc}")
        return 0

    runs: dict[str, dict[str, int]] = defaultdict(lambda: {"pass": 0, "fail": 0})
    for tc in root.iter("testcase"):
        # Offload writes the full "path::test" string in `name` and leaves
        # `classname` empty. Fall back to classname::name for compatibility
        # with other JUnit producers.
        name = tc.get("name") or ""
        classname = tc.get("classname") or ""
        full = name if "::" in name else (f"{classname}::{name}" if classname else name)
        if tc.find("failure") is not None or tc.find("error") is not None:
            runs[full]["fail"] += 1
        else:
            runs[full]["pass"] += 1

    failed = sorted(name for name, c in runs.items() if c["fail"] > 0 and c["pass"] == 0)
    flaky = sorted(name for name, c in runs.items() if c["fail"] > 0 and c["pass"] > 0)

    print("=" * _BANNER_WIDTH)
    print(f"Offload test outcomes (parsed from {junit_path})")
    print("=" * _BANNER_WIDTH)

    if not failed and not flaky:
        print("All tests passed (no failures, no flakes).")
        return 0

    if failed:
        print(f"\nFailed tests ({len(failed)}) — failed every run:")
        for name in failed:
            print(f"  {name}")

    if flaky:
        print(f"\nFlaky tests ({len(flaky)}) — failed at least once but passed on retry:")
        for name in flaky:
            print(f"  {name}")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
