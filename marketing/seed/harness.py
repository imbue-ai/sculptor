"""Ensure the demo QA harness is running; boot it if it isn't.

Launches sculptor.testing.manual_test_server (isolated backend + headless
Chromium) against the demo clone of the sculptor repo, with the demo
environment wired in:

  - the gh shim directory is prepended to PATH, so the backend's PR polling
    renders pills from marketing/gh_shim fixtures instead of contacting GitHub
  - SCULPTOR_DEMO_GH_FIXTURES points at the fixtures file seed_all.py writes
  - TESTING__FAKE_MODEL_DISPLAY_NAME renders the scripted FakeClaude agents
    as "Fable" and hides the testing models from the model picker

Idempotent: if the control API already answers, it reports the ports and
exits. Ports are parsed from the server log and written to
<demo dir>/screenshots/{control,backend}_port.txt for the other tools
(harness_client.py, shots/control.sh).

Run from the repo root:
  uv run --project sculptor python marketing/seed/harness.py
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (
    BACKEND_PORT_FILE,
    CONTROL_PORT_FILE,
    GH_FIXTURES_PATH,
    GH_SHIM_DIR,
    REPO_ROOT,
    SCREENSHOTS_DIR,
    SERVER_LOG,
    SERVER_PID_FILE,
)
from repos import ensure_clone

FAKE_MODEL_DISPLAY_NAME = "Fable"


def _is_control_alive() -> bool:
    # OSError covers the whole liveness-probe failure surface (missing port
    # file, refused/timed-out connection, HTTP errors); ValueError covers a
    # garbage port turning the URL invalid. Anything else should propagate.
    try:
        port = CONTROL_PORT_FILE.read_text().strip()
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/status", timeout=2) as resp:
            return b"success" in resp.read()
    except (OSError, ValueError):
        return False


def _demo_environment() -> dict[str, str]:
    env = dict(os.environ)
    env["PATH"] = f"{GH_SHIM_DIR}:{env.get('PATH', '')}"
    env["SCULPTOR_DEMO_GH_FIXTURES"] = str(GH_FIXTURES_PATH)
    env["TESTING__FAKE_MODEL_DISPLAY_NAME"] = FAKE_MODEL_DISPLAY_NAME
    return env


def _log_tail(max_lines: int = 20) -> str:
    if not SERVER_LOG.exists():
        return "(no server log)"
    return "\n".join(SERVER_LOG.read_text().splitlines()[-max_lines:])


def _parse_ports(process: subprocess.Popen, deadline_s: float = 180.0) -> tuple[str, str]:
    """Wait for the server log to reveal the control and backend ports."""
    deadline = time.time() + deadline_s
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"harness server exited with code {process.returncode} before publishing its ports; "
                f"log tail ({SERVER_LOG}):\n{_log_tail()}"
            )
        log = SERVER_LOG.read_text() if SERVER_LOG.exists() else ""
        control_match = re.search(r"MANUAL_TEST_CONTROL_PORT=(\d+)", log)
        # The backend restarts move the port, so take the LAST uvicorn line.
        backend_matches = re.findall(r"Uvicorn running on https?://[^:]+:(\d+)", log)
        if control_match and backend_matches:
            return control_match.group(1), backend_matches[-1]
        time.sleep(2)
    raise RuntimeError(f"harness did not come up within {deadline_s:.0f}s — see {SERVER_LOG}")


def _terminate_stale_server(wait_s: float = 10.0) -> None:
    """SIGTERM any prior harness instance and wait for it to actually exit.

    The old process owns the server log; truncating and reusing the log while
    it is still shutting down would interleave two servers' output (and let
    `_parse_ports` read the dying instance's ports).
    """
    if not SERVER_PID_FILE.exists():
        return
    try:
        pid = int(SERVER_PID_FILE.read_text().strip())
        os.kill(pid, signal.SIGTERM)
    except (OSError, ValueError) as e:
        # Stale or garbled pid file — nothing left to stop.
        print(f"note: could not signal prior harness ({e}); assuming it is gone")
        return
    deadline = time.time() + wait_s
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.2)
    print(f"note: prior harness (pid {pid}) still alive {wait_s:.0f}s after SIGTERM; continuing anyway")


def main() -> None:
    if _is_control_alive():
        if not BACKEND_PORT_FILE.exists():
            raise RuntimeError(
                f"harness state is inconsistent: the control API is alive but {BACKEND_PORT_FILE} "
                "is missing. Kill the running manual_test_server process and re-run this script."
            )
        print(
            f"READY control={CONTROL_PORT_FILE.read_text().strip()} "
            f"backend={BACKEND_PORT_FILE.read_text().strip()} (already up)"
        )
        return

    sculptor_clone = ensure_clone("sculptor")
    assert sculptor_clone is not None  # the sculptor repo always resolves (this checkout)
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    _terminate_stale_server()
    SERVER_LOG.write_text("")

    with open(SERVER_LOG, "ab") as log:
        process = subprocess.Popen(
            [
                "uv",
                "run",
                "--project",
                "sculptor",
                "python",
                "-m",
                "sculptor.testing.manual_test_server",
                "--project-path",
                sculptor_clone["path"],
                "--screenshots-dir",
                str(SCREENSHOTS_DIR),
            ],
            cwd=REPO_ROOT,
            env=_demo_environment(),
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
    SERVER_PID_FILE.write_text(str(process.pid))

    control, backend = _parse_ports(process)
    CONTROL_PORT_FILE.write_text(control)
    BACKEND_PORT_FILE.write_text(backend)
    print(f"READY control={control} backend={backend}")


if __name__ == "__main__":
    main()
