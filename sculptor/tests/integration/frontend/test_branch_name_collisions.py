"""Integration tests for branch-name collision detection.

Verifies the collision handling in both WORKTREE (default) and CLONE
(opt-in) modes: the debounced inline check surfaces an error and disables
Create, so a colliding name can never be submitted. (The authoritative
backend re-check returning 409 remains as a race safety net, but is not
reachable through the UI once the inline check has resolved.)
"""

import re
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.user_config import enable_clone_workspaces
from sculptor.testing.pages.add_workspace_page import PlaywrightAddWorkspacePage
from sculptor.testing.playwright_utils import open_new_workspace_form
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story
from sculptor.testing.utils import get_playwright_modifier_key

COLLIDING_BRANCH = "alice/conflicting"


@pytest.fixture
def colliding_branch(sculptor_instance_: SculptorInstance) -> Iterator[str]:
    """Pre-create a branch in the fixture repo so the test can collide with it."""
    repo_path = sculptor_instance_.project_path
    subprocess.run(
        ["git", "-C", str(repo_path), "branch", COLLIDING_BRANCH],
        check=True,
        capture_output=True,
    )
    try:
        yield COLLIDING_BRANCH
    finally:
        subprocess.run(
            ["git", "-C", str(repo_path), "branch", "-D", COLLIDING_BRANCH],
            capture_output=True,
            check=False,
        )


def _no_new_worktree_metadata(repo_path: Path) -> bool:
    worktrees_dir = repo_path / ".git" / "worktrees"
    if not worktrees_dir.is_dir():
        return True
    return not any(worktrees_dir.iterdir())


@user_story("to see a clear error when my branch name collides with an existing branch (worktree mode)")
def test_worktree_mode_collision_blocks_creation(sculptor_instance_: SculptorInstance, colliding_branch: str) -> None:
    page = sculptor_instance_.page
    add_ws_page = PlaywrightAddWorkspacePage(page=page)

    # Worktree is the default — no mode-selector interaction needed.
    open_new_workspace_form(page)
    add_ws_page.get_workspace_name_input().fill("test")

    branch_input = add_ws_page.get_branch_name_input()
    expect(branch_input).to_be_visible()
    expect(branch_input).to_have_value(re.compile(r".+"))
    branch_input.fill(colliding_branch)

    collision_error = add_ws_page.get_branch_name_collision_error()
    expect(collision_error).to_be_visible()
    expect(collision_error).to_contain_text(colliding_branch)
    expect(collision_error).to_contain_text("already exists")

    # The inline collision disables Create; a keyboard submit attempt is a
    # guarded no-op — no workspace is created and we stay on the create surface.
    expect(add_ws_page.get_submit_button()).to_be_disabled()
    page.keyboard.press(f"{get_playwright_modifier_key()}+Enter")

    chat_panel = page.get_by_test_id(ElementIDs.CHAT_PANEL)
    expect(chat_panel).not_to_be_visible()

    assert _no_new_worktree_metadata(sculptor_instance_.project_path), (
        "blocked submit should not leave a stale worktree metadata entry"
    )


@user_story("to see a clear error when my branch name collides with an existing branch (clone mode)")
def test_clone_mode_collision_blocks_creation(sculptor_instance_: SculptorInstance, colliding_branch: str) -> None:
    page = sculptor_instance_.page
    add_ws_page = PlaywrightAddWorkspacePage(page=page)

    # Clone is opt-in; enable the flag and pick clone mode explicitly.
    enable_clone_workspaces(page)

    open_new_workspace_form(page)
    add_ws_page.get_workspace_name_input().fill("test")
    add_ws_page.select_mode(ElementIDs.MODE_OPTION_CLONE)

    branch_input = add_ws_page.get_branch_name_input()
    expect(branch_input).to_be_visible()
    expect(branch_input).to_have_value(re.compile(r".+"))
    branch_input.fill(colliding_branch)

    collision_error = add_ws_page.get_branch_name_collision_error()
    expect(collision_error).to_be_visible()
    expect(collision_error).to_contain_text(colliding_branch)

    # Same blocked-create contract as worktree mode: Create disables and a
    # keyboard submit attempt is a guarded no-op.
    expect(add_ws_page.get_submit_button()).to_be_disabled()
    page.keyboard.press(f"{get_playwright_modifier_key()}+Enter")

    chat_panel = page.get_by_test_id(ElementIDs.CHAT_PANEL)
    expect(chat_panel).not_to_be_visible()
