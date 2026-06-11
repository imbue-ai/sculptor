"""Integration tests for branch-name collision detection.

Verifies the dual-layer collision check (debounced inline error +
authoritative backend re-check returning 409) in both WORKTREE and
CLONE modes.
"""

import re
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.user_config import enable_worktree_workspaces
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


def _select_worktree_mode(page) -> None:
    page.get_by_test_id(ElementIDs.MODE_SELECTOR).click()
    page.get_by_test_id(ElementIDs.MODE_OPTION_WORKTREE).click()


def _no_new_worktree_metadata(repo_path: Path) -> bool:
    worktrees_dir = repo_path / ".git" / "worktrees"
    if not worktrees_dir.is_dir():
        return True
    return not any(worktrees_dir.iterdir())


@user_story("to see a clear error when my branch name collides with an existing branch (worktree mode)")
def test_worktree_mode_collision_blocks_creation(sculptor_instance_: SculptorInstance, colliding_branch: str) -> None:
    page = sculptor_instance_.page
    enable_worktree_workspaces(page)

    navigate_to_add_workspace_page(page)
    page.get_by_test_id(ElementIDs.WORKSPACE_NAME_INPUT).fill("test")
    _select_worktree_mode(page)

    branch_input = page.get_by_test_id(ElementIDs.BRANCH_NAME_INPUT)
    expect(branch_input).to_be_visible()
    expect(branch_input).to_have_value(re.compile(r".+"), timeout=5_000)
    branch_input.fill(COLLIDING_BRANCH)

    collision_error = page.get_by_test_id(ElementIDs.BRANCH_NAME_COLLISION_ERROR)
    expect(collision_error).to_be_visible(timeout=5_000)
    expect(collision_error).to_contain_text(colliding_branch)
    expect(collision_error).to_contain_text("already exists")

    page.get_by_test_id(ElementIDs.START_TASK_BUTTON).click()

    # Submit should fail — the chat panel should NOT appear (we stay on Add Workspace).
    chat_panel = page.get_by_test_id(ElementIDs.CHAT_PANEL)
    expect(chat_panel).not_to_be_visible(timeout=5_000)

    assert _no_new_worktree_metadata(sculptor_instance_.project_path), (
        "failed submit should not leave a stale worktree metadata entry"
    )


@user_story("to see a clear error when my branch name collides with an existing branch (clone mode)")
def test_clone_mode_collision_blocks_creation(sculptor_instance_: SculptorInstance, colliding_branch: str) -> None:
    page = sculptor_instance_.page

    navigate_to_add_workspace_page(page)
    page.get_by_test_id(ElementIDs.WORKSPACE_NAME_INPUT).fill("test")

    branch_input = page.get_by_test_id(ElementIDs.BRANCH_NAME_INPUT)
    expect(branch_input).to_be_visible()
    expect(branch_input).to_have_value(re.compile(r".+"), timeout=5_000)
    branch_input.fill(COLLIDING_BRANCH)

    collision_error = page.get_by_test_id(ElementIDs.BRANCH_NAME_COLLISION_ERROR)
    expect(collision_error).to_be_visible(timeout=5_000)
    expect(collision_error).to_contain_text(colliding_branch)

    page.get_by_test_id(ElementIDs.START_TASK_BUTTON).click()

    chat_panel = page.get_by_test_id(ElementIDs.CHAT_PANEL)
    expect(chat_panel).not_to_be_visible(timeout=5_000)
