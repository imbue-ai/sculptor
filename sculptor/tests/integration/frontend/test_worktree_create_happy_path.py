"""Integration tests for the worktree workspace happy path.

Covers the three scenarios from the spec:
1. Default branch name: preview auto-fills → submit → worktree created.
2. Custom branch name: user overrides preview before submit.
3. Random slug: empty workspace name → preview uses `<user>/<adj>-<noun>`.

Worktree mode is the default; no flag toggling is needed and the mode
selector is hidden unless an opt-in mode (clone or in-place) is enabled.
"""

import re
import subprocess
from pathlib import Path

from playwright.sync_api import expect

from sculptor.testing.pages.add_workspace_page import PlaywrightAddWorkspacePage
from sculptor.testing.playwright_utils import open_new_workspace_form
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


def _wait_for_branch_preview(add_ws_page: PlaywrightAddWorkspacePage, expected_regex: str) -> str:
    """Wait for the branch-name input to match `expected_regex` and return its value."""
    branch_input = add_ws_page.get_branch_name_input()
    expect(branch_input).to_be_visible()
    expect(branch_input).to_have_value(re.compile(expected_regex))
    return branch_input.input_value()


@user_story("to create a worktree workspace using the auto-filled branch name")
def test_worktree_create_with_default_branch_name(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page

    open_new_workspace_form(page)
    add_ws_page = PlaywrightAddWorkspacePage(page)
    add_ws_page.get_workspace_name_input().fill("Fix login bug")

    branch_name = _wait_for_branch_preview(add_ws_page, r".*fix-login-bug$")

    add_ws_page.submit_and_wait_for_chat_panel()

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

    open_new_workspace_form(page)
    add_ws_page = PlaywrightAddWorkspacePage(page)
    add_ws_page.get_workspace_name_input().fill("Some task")
    _wait_for_branch_preview(add_ws_page, r".+")

    custom_name = "alice/scu-42-custom"
    branch_input = add_ws_page.get_branch_name_input()
    branch_input.fill(custom_name)
    expect(branch_input).to_have_value(custom_name)

    add_ws_page.submit_and_wait_for_chat_panel()

    paths = _worktree_paths(sculptor_instance_.project_path)
    assert paths, "no worktree created"
    worktree_path = paths[-1]
    assert _git_branch(worktree_path) == custom_name


@user_story("to create a worktree workspace with an empty workspace name (random slug)")
def test_worktree_create_with_empty_workspace_name_random_slug(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page

    open_new_workspace_form(page)
    add_ws_page = PlaywrightAddWorkspacePage(page)

    branch_name = _wait_for_branch_preview(add_ws_page, r".*[a-z0-9]+-[a-z0-9]+$")

    add_ws_page.submit_and_wait_for_chat_panel()

    paths = _worktree_paths(sculptor_instance_.project_path)
    assert paths, "no worktree created"
    worktree_path = paths[-1]
    assert _git_branch(worktree_path) == branch_name
