"""Integration tests for branch-name collision detection.

Verifies the dual-layer collision check (debounced inline error +
authoritative backend re-check returning 409) in both WORKTREE and
CLONE modes.
"""

import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import expect

from sculptor.testing.elements.user_config import enable_clone_workspaces
from sculptor.testing.pages.add_workspace_page import PlaywrightAddWorkspacePage
from sculptor.testing.playwright_utils import navigate_to_add_workspace_page
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# The fixture repo's git user.name is "imbue" (see repo_resources.py),
# which the backend slugifies into the `imbue/` prefix when auto-filling.
# Pre-create a branch matching that shape so typing the full name
# triggers a collision against an existing branch.
COLLIDING_BRANCH = "imbue/conflicting"


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

    # Worktree is the default mode — no flag or mode selection needed.
    navigate_to_add_workspace_page(page)
    add_workspace = PlaywrightAddWorkspacePage(page=page)
    add_workspace.get_workspace_name_input().fill("test")

    add_workspace.wait_for_branch_preview()
    add_workspace.get_branch_name_input().fill(COLLIDING_BRANCH)

    collision_error = add_workspace.get_branch_name_collision_error()
    expect(collision_error).to_be_visible()
    expect(collision_error).to_contain_text(colliding_branch)
    expect(collision_error).to_contain_text("already exists")

    add_workspace.get_submit_button().click()

    # Submit should fail — the chat panel should NOT appear (we stay on the
    # modal) and no worktree metadata should be left behind.
    expect(add_workspace.get_chat_panel()).not_to_be_visible()
    expect(add_workspace.get_new_workspace_modal()).to_be_visible()

    assert _no_new_worktree_metadata(sculptor_instance_.project_path), (
        "failed submit should not leave a stale worktree metadata entry"
    )


@user_story("to see a clear error when my branch name collides with an existing branch (clone mode)")
def test_clone_mode_collision_blocks_creation(sculptor_instance_: SculptorInstance, colliding_branch: str) -> None:
    page = sculptor_instance_.page
    enable_clone_workspaces(page)

    navigate_to_add_workspace_page(page)
    add_workspace = PlaywrightAddWorkspacePage(page=page)
    add_workspace.get_workspace_name_input().fill("test")
    add_workspace.select_clone_mode()

    add_workspace.wait_for_branch_preview()
    add_workspace.get_branch_name_input().fill(COLLIDING_BRANCH)

    collision_error = add_workspace.get_branch_name_collision_error()
    expect(collision_error).to_be_visible()
    expect(collision_error).to_contain_text(colliding_branch)

    add_workspace.get_submit_button().click()

    expect(add_workspace.get_chat_panel()).not_to_be_visible()
    expect(add_workspace.get_new_workspace_modal()).to_be_visible()
