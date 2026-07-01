"""Integration test for branch-name *validity* in the Add Workspace form.

Sibling to test_branch_name_collisions.py: verifies the dual-layer check for an
illegal git ref name (debounced inline error + authoritative backend rejection
at submit). A name that isn't a legal ref must surface a clear inline error and
must not create a workspace — historically it slipped through and only failed
later, deep in async environment setup, as an opaque WorktreeError.
"""

import re
from pathlib import Path

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.pages.add_workspace_page import PlaywrightAddWorkspacePage
from sculptor.testing.playwright_utils import navigate_to_add_workspace_page
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# Not a legal git ref: contains a space, a colon, and parentheses.
INVALID_BRANCH_NAME = "feature: my (broken) branch"


def _no_new_worktree_metadata(repo_path: Path) -> bool:
    worktrees_dir = repo_path / ".git" / "worktrees"
    if not worktrees_dir.is_dir():
        return True
    return not any(worktrees_dir.iterdir())


@user_story("to see a clear error when my branch name isn't a valid git ref (worktree mode)")
def test_worktree_mode_invalid_branch_name_blocks_creation(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    add_ws_page = PlaywrightAddWorkspacePage(page=page)

    # Worktree is the default — no mode-selector interaction needed.
    navigate_to_add_workspace_page(page)
    add_ws_page.get_workspace_name_input().fill("test")

    branch_input = add_ws_page.get_branch_name_input()
    expect(branch_input).to_be_visible()
    expect(branch_input).to_have_value(re.compile(r".+"))
    branch_input.fill(INVALID_BRANCH_NAME)

    invalid_error = add_ws_page.get_branch_name_invalid_error()
    expect(invalid_error).to_be_visible()
    expect(invalid_error).to_contain_text("not a valid branch name")

    add_ws_page.get_submit_button().click()

    # Submit must fail — the chat panel should NOT appear (we stay on Add Workspace).
    chat_panel = page.get_by_test_id(ElementIDs.CHAT_PANEL)
    expect(chat_panel).not_to_be_visible()

    assert _no_new_worktree_metadata(sculptor_instance_.project_path), (
        "failed submit should not leave a stale worktree metadata entry"
    )
