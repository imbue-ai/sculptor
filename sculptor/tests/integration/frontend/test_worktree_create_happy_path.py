"""Integration tests for the worktree workspace happy path.

Covers the three scenarios from the spec:
1. Default branch name: flag on → preview auto-fills → submit → worktree created.
2. Custom branch name: user overrides preview before submit.
3. Random slug: empty workspace name → preview uses `<user>/<adj>-<noun>`.
"""

import re
import subprocess
from pathlib import Path

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.user_config import enable_worktree_workspaces
from sculptor.testing.playwright_utils import navigate_to_add_workspace_page
from sculptor.testing.playwright_utils import read_branch_name_field
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _worktree_paths(user_repo_path: Path) -> list[Path]:
    """Return all worktree paths (except the main one) for the user's repo."""
    result = subprocess.run(
        ["git", "-C", str(user_repo_path), "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    paths: list[Path] = []
    main_path = user_repo_path.resolve()
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            p = Path(line.removeprefix("worktree ").strip()).resolve()
            if p != main_path:
                paths.append(p)
    return paths


def _git_remotes(worktree_path: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(worktree_path), "remote"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _git_branch(worktree_path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(worktree_path), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _wait_for_branch_preview(page, expected_regex: str, timeout_ms: int = 5000) -> str:
    """Wait for the branch-name field to match `expected_regex` and return its value."""
    branch_input = page.get_by_test_id(ElementIDs.BRANCH_NAME_INPUT)
    expect(branch_input).to_be_visible(timeout=timeout_ms)
    expect(branch_input).to_have_value(re.compile(expected_regex), timeout=timeout_ms)
    return read_branch_name_field(page)


def _select_worktree_mode(page) -> None:
    page.get_by_test_id(ElementIDs.MODE_SELECTOR).click()
    page.get_by_test_id(ElementIDs.MODE_OPTION_WORKTREE).click()


def _submit_and_wait_for_ready(page) -> None:
    submit_button = page.get_by_test_id(ElementIDs.START_TASK_BUTTON)
    expect(submit_button).to_be_enabled()
    submit_button.click()
    chat_panel = page.get_by_test_id(ElementIDs.CHAT_PANEL)
    expect(chat_panel).to_be_visible(timeout=60_000)


@user_story("to create a worktree workspace using the auto-filled branch name")
def test_worktree_create_with_default_branch_name(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    enable_worktree_workspaces(page)

    navigate_to_add_workspace_page(page)
    workspace_name_input = page.get_by_test_id(ElementIDs.WORKSPACE_NAME_INPUT)
    workspace_name_input.fill("Fix login bug")
    _select_worktree_mode(page)

    branch_name = _wait_for_branch_preview(page, r".*fix-login-bug.*")
    assert branch_name.endswith("fix-login-bug"), f"expected slug to end in fix-login-bug, got: {branch_name!r}"

    _submit_and_wait_for_ready(page)

    paths = _worktree_paths(sculptor_instance_.project_path)
    assert paths, "no worktree created"
    worktree_path = paths[-1]
    assert worktree_path.exists(), f"worktree path does not exist: {worktree_path}"
    assert _git_branch(worktree_path) == branch_name
    remotes = _git_remotes(worktree_path)
    assert "local" not in remotes, f"worktree should not have a local remote; got {remotes!r}"


@user_story("to create a worktree workspace with a custom branch name")
def test_worktree_create_with_custom_branch_name(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    enable_worktree_workspaces(page)

    navigate_to_add_workspace_page(page)
    page.get_by_test_id(ElementIDs.WORKSPACE_NAME_INPUT).fill("Some task")
    _select_worktree_mode(page)
    _wait_for_branch_preview(page, r".+")

    custom_branch = "imbue/scu-42-custom"
    branch_input = page.get_by_test_id(ElementIDs.BRANCH_NAME_INPUT)
    branch_input.fill(custom_branch)
    expect(branch_input).to_have_value(custom_branch)
    full_branch = read_branch_name_field(page)
    assert full_branch == custom_branch, f"expected branch {custom_branch!r}, got: {full_branch!r}"

    _submit_and_wait_for_ready(page)

    paths = _worktree_paths(sculptor_instance_.project_path)
    assert paths, "no worktree created"
    worktree_path = paths[-1]
    assert _git_branch(worktree_path) == full_branch


@user_story("to create a worktree workspace with an empty workspace name (random slug)")
def test_worktree_create_with_empty_workspace_name_random_slug(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    enable_worktree_workspaces(page)

    navigate_to_add_workspace_page(page)
    _select_worktree_mode(page)

    branch_name = _wait_for_branch_preview(page, r".*[a-z0-9]+-[a-z0-9]+$")
    assert re.search(r"[a-z0-9]+-[a-z0-9]+$", branch_name), (
        f"expected a two-word random slug at the end, got: {branch_name!r}"
    )

    _submit_and_wait_for_ready(page)

    paths = _worktree_paths(sculptor_instance_.project_path)
    assert paths, "no worktree created"
    worktree_path = paths[-1]
    assert _git_branch(worktree_path) == branch_name
