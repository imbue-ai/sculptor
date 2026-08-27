"""Integration tests for the mobile full-screen overlays: review-all and terminal.

Both overlays float over the chat as in-shell state — "back" closes them and
returns to the chat rather than navigating the router.
"""

import pytest
from playwright.sync_api import expect

from sculptor.testing.elements.mobile_workspace import enter_mobile_workspace
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

pytestmark = pytest.mark.mobile


@user_story("to review all changes full-screen from my phone")
def test_mobile_review_all_overlay(sculptor_instance_: SculptorInstance) -> None:
    """The ChangesPill opens a full-screen review-all overlay: the combined diff
    with its desktop toolbar hidden and the commit action pinned in a footer."""
    page = sculptor_instance_.page

    # Write a file so there are uncommitted changes for the pill to surface.
    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:write_file `{"file_path": "mobile_change.txt", "content": "hello from mobile\\n"}`',
    )
    shell = enter_mobile_workspace(page)

    changes_pill = shell.get_changes_pill()
    expect(changes_pill.root()).to_be_visible()

    overlay = changes_pill.open_review_all()
    expect(overlay.root()).to_be_visible()
    # The combined diff renders the changed file...
    expect(overlay.get_diff_file_sections().first).to_be_visible()
    # ...with the desktop file-nav/scope toolbar hidden...
    expect(overlay.get_diff_toolbar()).to_have_count(0)
    # ...and the commit action pinned in the footer.
    expect(overlay.get_commit_button()).to_be_visible()

    # Back returns to the chat.
    overlay.back()
    expect(shell.get_chat_panel().get_chat_input()).to_be_visible()


@user_story("to open a terminal full-screen from my phone")
def test_mobile_terminal_overlay(sculptor_instance_: SculptorInstance) -> None:
    """The header ⋮ menu opens a full-screen terminal overlay wrapping the real
    terminal panel; back returns to the chat."""
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(sculptor_page=page)
    shell = enter_mobile_workspace(page)

    overlay = shell.open_terminal_overlay()
    expect(overlay.root()).to_be_visible()
    expect(overlay.get_terminal_panel()).to_be_visible()

    # Back closes the overlay (it already asserts the overlay is gone) and returns
    # to the chat.
    overlay.back()
    expect(shell.get_chat_panel().get_chat_input()).to_be_visible()
