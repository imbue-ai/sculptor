"""Integration test for branch-name *validity* in the new-workspace form.

Sibling to test_branch_name_collisions.py: verifies the inline check for an
illegal git ref name. The branch field sanitizes most illegal characters as the
user types (spaces, colons, reserved ref characters are stripped or collapsed),
so only the trailing-position violations the sanitizer deliberately leaves
alone — a ``.lock`` suffix, a trailing ``.`` or ``/`` — can reach the debounced
validity check. Those must surface a clear inline error and disable Create, so
an invalid name can never be submitted (historically it slipped through and
only failed later, deep in async environment setup, as an opaque
WorktreeError).
"""

import re
from pathlib import Path

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.pages.add_workspace_page import PlaywrightAddWorkspacePage
from sculptor.testing.playwright_utils import open_new_workspace_form
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story
from sculptor.testing.utils import get_playwright_modifier_key

# Not a legal git ref (a ".lock" suffix), yet it survives the as-you-type
# sanitizer — which strips spaces/colons/parens on entry — so it exercises the
# debounced validity check rather than the sanitizer.
INVALID_BRANCH_NAME = "bad.lock"


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
    open_new_workspace_form(page)
    add_ws_page.get_workspace_name_input().fill("test")

    branch_input = add_ws_page.get_branch_name_input()
    expect(branch_input).to_be_visible()
    expect(branch_input).to_have_value(re.compile(r".+"))
    branch_input.fill(INVALID_BRANCH_NAME)
    # The sanitizer leaves the trailing-position violation intact for the
    # debounced check to catch — guard that assumption before asserting on it.
    expect(branch_input).to_have_value(INVALID_BRANCH_NAME)

    invalid_error = add_ws_page.get_branch_name_invalid_error()
    expect(invalid_error).to_be_visible()
    expect(invalid_error).to_contain_text("not a valid branch name")

    # The inline invalid error disables Create; a keyboard submit attempt is a
    # guarded no-op — no workspace is created and we stay on the create surface.
    expect(add_ws_page.get_submit_button()).to_be_disabled()
    page.keyboard.press(f"{get_playwright_modifier_key()}+Enter")

    chat_panel = page.get_by_test_id(ElementIDs.CHAT_PANEL)
    expect(chat_panel).not_to_be_visible()

    assert _no_new_worktree_metadata(sculptor_instance_.project_path), (
        "blocked submit should not leave a stale worktree metadata entry"
    )
