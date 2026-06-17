"""Integration tests for `sculpt ui open-file`.

Each test launches a workspace, runs the CLI verb in-band, then asserts
on the per-workspace diff-panel state via Playwright.

The CLI subprocess inherits its cwd from pytest, NOT from the workspace
clone. Tests therefore use absolute paths (a tempfile or a known absolute
path) so the relative-to-cwd resolution doesn't surface unrelated paths
to the backend. The relaxed read-file gate makes any
host-readable absolute path acceptable, which is what these tests rely on.
"""

import contextlib
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Generator
from pathlib import Path

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.diff_panel import get_diff_panel_from_page
from sculptor.testing.elements.file_browser import get_file_browser_panel
from sculptor.testing.playwright_utils import request_with_retry
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _extract_workspace_id_from_url(url: str) -> str:
    match = re.search(r"/ws/([a-zA-Z0-9_-]+)/", url)
    assert match is not None, f"Could not extract workspace ID from URL: {url}"
    return match.group(1)


def _run_sculpt_ui_open_file(
    instance: SculptorInstance,
    *,
    path: str,
    workspace_id: str,
    mode: str | None = None,
    timeout_seconds: float = 30.0,
) -> tuple[int, str, str]:
    """Run `sculpt ui open-file` against the running Sculptor backend.

    Returns (exit_code, stdout, stderr).
    """
    args = ["ui", "open-file", path, "-w", workspace_id, "--base-url", instance.backend_api_url]
    if mode is not None:
        args += ["--mode", mode]

    env = {**os.environ}
    result = subprocess.run(
        [sys.executable, "-m", "sculpt.main"] + args,
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout_seconds,
    )
    return result.returncode, result.stdout, result.stderr


_NO_OP_PROMPT = """\
fake_claude:text `{"text": "ready"}`"""


def _start_empty_workspace(page: Page) -> str:
    """Start a workspace and return its workspace_id with no agent activity."""
    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=_NO_OP_PROMPT,
        wait_for_agent_to_finish=True,
    )
    return _extract_workspace_id_from_url(page.url)


@contextlib.contextmanager
def _workspace_and_file(
    page: Page, *, suffix: str = ".txt", content: str = "hello\n"
) -> Generator[tuple[str, str], None, None]:
    """Yield (workspace_id, absolute_file_path).

    Creates an empty workspace and a tempfile that the backend can read via
    the relaxed read-file gate. Cleans the tempfile up on exit.
    """
    workspace_id = _start_empty_workspace(page)
    with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        yield workspace_id, tmp_path
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@user_story("agent surfaces a file via sculpt ui open-file --mode file")
def test_mode_file_opens_file_view_tab(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    with _workspace_and_file(page) as (workspace_id, file_path):
        exit_code, _stdout, stderr = _run_sculpt_ui_open_file(
            sculptor_instance_, path=file_path, workspace_id=workspace_id, mode="file"
        )
        assert exit_code == 0, f"Expected exit 0, got {exit_code}; stderr: {stderr}"

        diff_panel = get_diff_panel_from_page(page)
        expect(diff_panel).to_be_visible()

        file_tab = diff_panel.get_tab_by_name(Path(file_path).name)
        expect(file_tab.first).to_be_visible()

        preview = diff_panel.get_read_only_preview()
        expect(preview).to_be_visible()


@user_story("agent surfaces a file with --mode diff")
def test_mode_diff_opens_single_tab(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    with _workspace_and_file(page) as (workspace_id, file_path):
        exit_code, _stdout, stderr = _run_sculpt_ui_open_file(
            sculptor_instance_, path=file_path, workspace_id=workspace_id, mode="diff"
        )
        assert exit_code == 0, f"Expected exit 0, got {exit_code}; stderr: {stderr}"

        diff_panel = get_diff_panel_from_page(page)
        expect(diff_panel).to_be_visible()

        file_tab = diff_panel.get_tab_by_name(Path(file_path).name)
        expect(file_tab.first).to_be_visible()


@user_story("agent surfaces a file with default --mode auto")
def test_mode_auto_opens_a_tab(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    with _workspace_and_file(page) as (workspace_id, file_path):
        exit_code, _stdout, stderr = _run_sculpt_ui_open_file(
            sculptor_instance_, path=file_path, workspace_id=workspace_id
        )
        assert exit_code == 0, f"Expected exit 0, got {exit_code}; stderr: {stderr}"

        diff_panel = get_diff_panel_from_page(page)
        expect(diff_panel).to_be_visible()

        file_tab = diff_panel.get_tab_by_name(Path(file_path).name)
        expect(file_tab.first).to_be_visible()


@user_story("CLI exits 3 when the workspace is closed")
def test_closed_workspace_exits_3(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    workspace_id = _start_empty_workspace(page)

    # Close the workspace via the API.
    base_url = sculptor_instance_.backend_api_url.rstrip("/")
    response = request_with_retry(
        page.request.patch,
        f"{base_url}/api/v1/workspaces/{workspace_id}",
        data={"is_open": False},
    )
    assert response.ok, f"Failed to close workspace: HTTP {response.status}"

    exit_code, _stdout, stderr = _run_sculpt_ui_open_file(
        sculptor_instance_, path="/tmp/anything.txt", workspace_id=workspace_id, mode="file"
    )
    assert exit_code == 3, f"Expected exit 3 (workspace_not_open), got {exit_code}; stderr: {stderr}"
    assert "not open" in stderr.lower()


@user_story("CLI exits 4 when the path does not exist")
def test_path_not_found_exits_4(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    workspace_id = _start_empty_workspace(page)

    exit_code, _stdout, stderr = _run_sculpt_ui_open_file(
        sculptor_instance_,
        path="/nonexistent/path/that/does/not/exist.txt",
        workspace_id=workspace_id,
        mode="file",
    )
    assert exit_code == 4, f"Expected exit 4 (file_not_found), got {exit_code}; stderr: {stderr}"


@user_story("agent can open an out-of-clone host-readable file via absolute path")
def test_out_of_clone_absolute_path_opens(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    with _workspace_and_file(page, content="hello from out-of-clone\n") as (workspace_id, tmp_path):
        exit_code, _stdout, stderr = _run_sculpt_ui_open_file(
            sculptor_instance_, path=tmp_path, workspace_id=workspace_id, mode="file"
        )
        assert exit_code == 0, f"Expected exit 0, got {exit_code}; stderr: {stderr}"

        diff_panel = get_diff_panel_from_page(page)
        expect(diff_panel).to_be_visible()

        file_tab = diff_panel.get_tab_by_name(Path(tmp_path).name)
        expect(file_tab.first).to_be_visible()


@user_story("diff panel auto-opens when an open-file event arrives in a fresh session")
def test_panel_auto_opens(sculptor_instance_: SculptorInstance) -> None:
    """An OpenFileUiAction event must force isOpen=true.

    The panel starts hidden after a fresh workspace creation; running the CLI
    once should make it visible. setActiveDiffTabAtom (the underlying atom)
    sets isOpen=true unconditionally, so this exercises the auto-expand
    branch without needing a separate "collapse first" step.
    """
    page = sculptor_instance_.page
    with _workspace_and_file(page) as (workspace_id, file_path):
        diff_panel = get_diff_panel_from_page(page)

        exit_code, _stdout, stderr = _run_sculpt_ui_open_file(
            sculptor_instance_, path=file_path, workspace_id=workspace_id, mode="file"
        )
        assert exit_code == 0, f"Expected exit 0, got {exit_code}; stderr: {stderr}"
        expect(diff_panel).to_be_visible()


@user_story("opening the same file twice produces a single tab")
def test_same_path_same_kind_no_duplicate_tab(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    with _workspace_and_file(page) as (workspace_id, file_path):
        for _ in range(2):
            exit_code, _stdout, stderr = _run_sculpt_ui_open_file(
                sculptor_instance_, path=file_path, workspace_id=workspace_id, mode="file"
            )
            assert exit_code == 0, f"Expected exit 0, got {exit_code}; stderr: {stderr}"

        diff_panel = get_diff_panel_from_page(page)
        file_tabs = diff_panel.get_tab_by_name(Path(file_path).name)
        expect(file_tabs).to_have_count(1)


@user_story("opening the same path with different modes produces two distinct tabs")
def test_different_kind_same_path_creates_distinct_tabs(
    sculptor_instance_: SculptorInstance,
) -> None:
    page = sculptor_instance_.page
    with _workspace_and_file(page) as (workspace_id, file_path):
        exit_code_file, _stdout1, stderr1 = _run_sculpt_ui_open_file(
            sculptor_instance_, path=file_path, workspace_id=workspace_id, mode="file"
        )
        assert exit_code_file == 0, f"Expected exit 0 (file mode), got {exit_code_file}; stderr: {stderr1}"

        exit_code_diff, _stdout2, stderr2 = _run_sculpt_ui_open_file(
            sculptor_instance_, path=file_path, workspace_id=workspace_id, mode="diff"
        )
        assert exit_code_diff == 0, f"Expected exit 0 (diff mode), got {exit_code_diff}; stderr: {stderr2}"

        diff_panel = get_diff_panel_from_page(page)
        # The two activations produce two distinct tabs (different kind keys).
        expect(diff_panel.get_tab_by_name(Path(file_path).name)).to_have_count(2)


@user_story("opening a file while a combined-review tab is active leaves the combined tab in place")
def test_combined_tab_remains_when_open_file_arrives(
    sculptor_instance_: SculptorInstance,
) -> None:
    page = sculptor_instance_.page
    with _workspace_and_file(page) as (workspace_id, file_path):
        # Open Review All to surface the combined-diff tab if the button is exposed.
        file_browser = get_file_browser_panel(page)
        review_all_btn = file_browser.get_review_all_button()
        if review_all_btn.is_visible():
            review_all_btn.click()

        exit_code, _stdout, stderr = _run_sculpt_ui_open_file(
            sculptor_instance_, path=file_path, workspace_id=workspace_id, mode="file"
        )
        assert exit_code == 0, f"Expected exit 0, got {exit_code}; stderr: {stderr}"

        diff_panel = get_diff_panel_from_page(page)
        file_tab = diff_panel.get_tab_by_name(Path(file_path).name)
        expect(file_tab.first).to_be_visible()
