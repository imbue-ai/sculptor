"""Entry point for the manual testing live browser server.

Starts a Sculptor instance on the home page and serves an HTTP API for
interactive browser control. The agent navigates entirely by clicking
buttons — just like a real user. Designed to be invoked by the
auto-qa-changes skill::

    uv run --project sculptor python -m sculptor.testing.manual_test_server \\
        --screenshots-dir /path/to/screenshots

The agent then reads the control port from stdout and interacts via curl::

    curl http://127.0.0.1:<PORT>/screenshot
    curl -X POST http://127.0.0.1:<PORT>/execute -d '{"action":"click","x":100,"y":200}'
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

from sculptor.testing.browser_controller import BrowserController
from sculptor.testing.manual_test_harness import ManualTestHarness
from sculptor.testing.port_manager import PortManager


def main() -> None:
    parser = argparse.ArgumentParser(description="Manual testing live browser server")
    parser.add_argument(
        "--screenshots-dir",
        type=str,
        default=None,
        help="Directory for screenshots (default: auto-created temp dir)",
    )
    parser.add_argument(
        "--project-path",
        type=str,
        default=None,
        help="Path to a git repo to open in Sculptor (default: creates a test repo)",
    )
    parser.add_argument(
        "--viewport-width",
        type=int,
        default=1400,
        help="Browser viewport width (default: 1400)",
    )
    parser.add_argument(
        "--viewport-height",
        type=int,
        default=900,
        help="Browser viewport height (default: 900)",
    )
    args = parser.parse_args()

    screenshots_dir = Path(args.screenshots_dir) if args.screenshots_dir else None
    project_path = Path(args.project_path) if args.project_path else None

    # Auto-allocate a free port for the HTTP control API
    port_manager = PortManager()
    control_port = port_manager.get_free_port()

    harness = ManualTestHarness(
        screenshots_dir=screenshots_dir,
        viewport={"width": args.viewport_width, "height": args.viewport_height},
        project_path=project_path,
    )

    logger.info("Starting harness (backend + Vite dev server)...")

    try:
        harness.start()
    except Exception as e:
        logger.error("Failed to start harness: {}", e)
        harness.stop()
        port_manager.release_port(control_port)
        sys.exit(1)

    logger.info("Sculptor backend running at {}", harness.base_url)
    logger.info("Screenshots directory: {}", harness.screenshots_dir)

    # Print the control port in a parseable format so the agent can find it
    print(f"MANUAL_TEST_CONTROL_PORT={control_port}", flush=True)
    logger.info("Starting browser controller on port {}", control_port)

    controller = BrowserController(
        page=harness.page,
        screenshots_dir=harness.screenshots_dir,
        harness=harness,
    )

    try:
        controller.serve(port=control_port)
    except KeyboardInterrupt:
        logger.info("Interrupted — shutting down")
    finally:
        harness.stop()
        port_manager.release_port(control_port)


if __name__ == "__main__":
    main()
