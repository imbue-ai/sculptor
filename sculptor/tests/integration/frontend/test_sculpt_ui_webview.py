"""Integration tests for `sculpt ui webview-navigate` and `sculpt ui webview-refresh`.

The Browser panel itself is Electron-only — Playwright drives a web browser,
which renders the placeholder web-mode shell. These tests therefore focus on
what *is* observable through the headless harness: CLI exit codes against a
running backend, and the 404/3 mapping for missing/closed workspaces.

End-to-end coverage of the webview reacting to commands is documented in the
manual smoke runbook for the demo (see Task 1.4 of the implementation plan).
"""

import re
import subprocess
import sys

from playwright.sync_api import Page

from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _extract_workspace_id_from_url(url: str) -> str:
    match = re.search(r"/ws/([a-zA-Z0-9_-]+)/", url)
    assert match is not None, f"Could not extract workspace ID from URL: {url}"
    return match.group(1)


def _run_sculpt_ui(
    instance: SculptorInstance,
    *args: str,
    timeout_seconds: float = 30.0,
) -> tuple[int, str, str]:
    result = subprocess.run(
        [sys.executable, "-m", "sculpt.main", "ui", *args, "--base-url", instance.base_url],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    return result.returncode, result.stdout, result.stderr


_NO_OP_PROMPT = """\
fake_claude:text `{"text": "ready"}`"""


def _start_empty_workspace(page: Page) -> str:
    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=_NO_OP_PROMPT,
        wait_for_agent_to_finish=True,
    )
    return _extract_workspace_id_from_url(page.url)


@user_story("agent navigates the browser panel via sculpt ui webview-navigate")
def test_agent_navigate_updates_browser_panel(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    workspace_id = _start_empty_workspace(page)

    exit_code, _stdout, stderr = _run_sculpt_ui(
        sculptor_instance_,
        "webview-navigate",
        "https://example.com",
        "-w",
        workspace_id,
    )
    assert exit_code == 0, f"Expected exit 0, got {exit_code}; stderr: {stderr}"


@user_story("agent refreshes the browser panel via sculpt ui webview-refresh")
def test_agent_refresh_emits_refresh_command(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    workspace_id = _start_empty_workspace(page)

    navigate_exit, _, navigate_stderr = _run_sculpt_ui(
        sculptor_instance_,
        "webview-navigate",
        "https://example.com",
        "-w",
        workspace_id,
    )
    assert navigate_exit == 0, f"navigate failed: {navigate_stderr}"

    refresh_exit, _, refresh_stderr = _run_sculpt_ui(
        sculptor_instance_,
        "webview-refresh",
        "-w",
        workspace_id,
    )
    assert refresh_exit == 0, f"refresh failed: {refresh_stderr}"


@user_story("CLI exits 3 when navigating a closed workspace")
def test_navigate_closed_workspace_exits_3(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    workspace_id = _start_empty_workspace(page)

    base_url = sculptor_instance_.base_url.rstrip("/")
    response = page.request.patch(
        f"{base_url}/api/v1/workspaces/{workspace_id}",
        data={"is_open": False},
    )
    assert response.ok, f"Failed to close workspace: HTTP {response.status}"

    exit_code, _stdout, stderr = _run_sculpt_ui(
        sculptor_instance_,
        "webview-navigate",
        "https://example.com",
        "-w",
        workspace_id,
    )
    assert exit_code == 3, f"Expected exit 3 (workspace_not_open), got {exit_code}; stderr: {stderr}"
    assert "not open" in stderr.lower()
