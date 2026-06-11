"""Integration tests for clone-mode branch-name field behavior.

Verifies the parallel branch-experience for CLONE mode (the field is
optional): clearing it checks out the base branch directly, keeping
the auto-filled value creates a new branch inside the clone.
"""

import re
import subprocess
from pathlib import Path

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.playwright_utils import navigate_to_add_workspace_page
from sculptor.testing.playwright_utils import read_branch_name_field
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _workspace_id_from_url(page: Page) -> str:
    expect(page).to_have_url(re.compile(r".*/ws/(ws_[a-z0-9]+)/"), timeout=10_000)
    match = re.search(r"/ws/(ws_[a-z0-9]+)/", page.url)
    assert match, f"could not extract workspace_id from URL: {page.url}"
    return match.group(1)


def _clone_code_dir_for_workspace(page: Page, workspace_id: str, timeout_ms: int = 30_000) -> Path:
    base_url = page.url.split("#")[0].rstrip("/")
    for _ in range(timeout_ms // 200):
        response = page.request.get(f"{base_url}/api/v1/workspaces/{workspace_id}")
        assert response.ok, f"GET workspace failed: {response.status} {response.text()}"
        environment_id = response.json().get("environmentId")
        if environment_id:
            return Path(environment_id) / "code"
        page.wait_for_timeout(200)
    raise AssertionError(f"workspace {workspace_id} never got an environment_id within {timeout_ms}ms")


def _git_branch(repo_path: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _branch_exists(repo_path: Path, branch: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo_path), "branch", "--list", branch],
        capture_output=True,
        text=True,
        check=True,
    )
    return bool(result.stdout.strip())


def _submit_and_wait_for_ready(page) -> None:
    submit_button = page.get_by_test_id(ElementIDs.START_TASK_BUTTON)
    expect(submit_button).to_be_enabled()
    submit_button.click()
    chat_panel = page.get_by_test_id(ElementIDs.CHAT_PANEL)
    expect(chat_panel).to_be_visible(timeout=60_000)


@user_story("to clone a repo and work on the base branch directly by clearing the branch-name field")
def test_clone_mode_cleared_branch_checks_out_base(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page

    navigate_to_add_workspace_page(page)
    page.get_by_test_id(ElementIDs.WORKSPACE_NAME_INPUT).fill("Some work")

    branch_input = page.get_by_test_id(ElementIDs.BRANCH_NAME_INPUT)
    expect(branch_input).to_be_visible()
    expect(branch_input).to_have_value(re.compile(r".+"), timeout=5_000)
    branch_input.fill("")
    expect(branch_input).to_have_value("")

    _submit_and_wait_for_ready(page)

    workspace_id = _workspace_id_from_url(page)
    clone_path = _clone_code_dir_for_workspace(page, workspace_id)
    current = _git_branch(clone_path)
    assert current in {"main", "master", "testing"}, f"unexpected base branch: {current!r}"
    assert not _branch_exists(clone_path, "test/some-work"), "clearing the branch field should not create a new branch"


@user_story("to clone a repo and work on a new branch using the auto-filled name")
def test_clone_mode_kept_branch_name_creates_new_branch(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page

    navigate_to_add_workspace_page(page)
    page.get_by_test_id(ElementIDs.WORKSPACE_NAME_INPUT).fill("Fix login bug")

    branch_input = page.get_by_test_id(ElementIDs.BRANCH_NAME_INPUT)
    expect(branch_input).to_be_visible()
    expect(branch_input).to_have_value(re.compile(r".*fix-login-bug.*"), timeout=5_000)
    expected_branch = read_branch_name_field(page)

    _submit_and_wait_for_ready(page)

    workspace_id = _workspace_id_from_url(page)
    clone_path = _clone_code_dir_for_workspace(page, workspace_id)
    assert _git_branch(clone_path) == expected_branch
    assert _branch_exists(clone_path, expected_branch)
