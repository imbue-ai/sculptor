"""End-to-end CLI tests against a live backend.

Most of the per-exit-code matrix for `sculpt ui open-file` is verified
two layers down:
  - tools/sculpt/tests/unit/test_ui.py — exit codes 0/2/3/4/5 with HTTP
    response mocking (respx).
  - sculptor/tests/integration/test_sculpt_ui_open_file.py — exit codes
    0/3/4 against a real Playwright-driven Sculptor instance.

This file holds the cases that don't need a backend at all (the no-server
exit-5 path), so the contract that "agent's tool harness sees exit 5
when Sculptor is not running" is verified end-to-end with the real
binary path, no respx mocking.
"""

import os
import subprocess
import sys


def test_ui_open_file_no_backend_exits_5() -> None:
    """When the backend is not running, the CLI must exit 5.

    Points at port 1 (TCPMUX, almost never bound) so the connection is
    refused immediately. The CLI's handle_connection_error path hits
    cli_error("Could not connect to Sculptor server", exit_code=5).
    """
    env = {**os.environ, "SCULPT_API_PORT": "1"}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "sculpt.main",
            "ui",
            "open-file",
            "/tmp/anything.txt",
            "-w",
            "ws_anything",
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )
    assert result.returncode == 5, (
        f"Expected exit 5, got {result.returncode}; stdout={result.stdout!r}; stderr={result.stderr!r}"
    )
    assert "Could not connect" in result.stderr


def test_ui_open_file_missing_workspace_exits_2() -> None:
    """When neither --workspace nor SCULPT_WORKSPACE_ID is set, the CLI exits 2
    (bad usage)."""
    env = {**os.environ}
    env.pop("SCULPT_WORKSPACE_ID", None)
    result = subprocess.run(
        [sys.executable, "-m", "sculpt.main", "ui", "open-file", "/tmp/x.txt"],
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )
    assert result.returncode == 2, (
        f"Expected exit 2, got {result.returncode}; stdout={result.stdout!r}; stderr={result.stderr!r}"
    )


def test_ui_open_file_invalid_mode_exits_2() -> None:
    """An unknown --mode value is a usage error → exit 2."""
    env = {**os.environ, "SCULPT_API_PORT": "1"}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "sculpt.main",
            "ui",
            "open-file",
            "/tmp/x.txt",
            "-w",
            "ws_anything",
            "--mode",
            "bogus",
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )
    assert result.returncode == 2, (
        f"Expected exit 2, got {result.returncode}; stdout={result.stdout!r}; stderr={result.stderr!r}"
    )
