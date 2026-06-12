"""Integration test for the workspace banner overflow menu (SCU-1372).

When the workspace banner is too narrow to show all of its items, the
progressive-collapse logic hides the lowest-priority items. Previously a "..."
overflow menu appeared in their place whose ``DropdownMenu.Item`` entries had no
``onSelect`` handler — a user could open the menu and click the items, but
nothing happened. They were inert placeholders for an overflow menu that was
never wired up.

This test forces the banner to collapse and asserts that no such inert overflow
menu is shown.
"""

from playwright.sync_api import expect

from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to not be shown collapsed-banner menu items that do nothing when clicked")
def test_collapsed_banner_has_no_inert_overflow_menu(
    sculptor_instance_: SculptorInstance,
) -> None:
    """A narrowed (collapsed) workspace banner must not render an inert
    overflow menu whose items have no effect."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        page,
        prompt='fake_claude:text `{"text": "Done"}`',
        workspace_name="Banner Overflow WS",
    )

    # Wait for the banner to fully render (branch name resolved, no skeleton)
    # so progressive collapse measures real content widths, not placeholders.
    task_page.get_branch_name_element()

    # At full width the repo segment is shown in the banner.
    repo_segment = task_page.get_repo_segment_button()
    expect(repo_segment).to_be_visible()

    # Shrink the viewport so the banner is far too narrow to fit its items,
    # which drives the progressive-collapse logic to hide the low-priority
    # items.
    original_size = page.viewport_size
    assert original_size is not None
    page.set_viewport_size({"width": 280, "height": original_size["height"]})

    # Confirm the banner actually entered its collapsed state: the repo segment
    # (collapse priority 2) is unmounted once horizontal space is constrained.
    expect(repo_segment).to_have_count(0)

    # The bug: a "..." overflow menu of inert items rendered here. After the
    # fix the collapse simply hides items with no dead menu in their place.
    expect(task_page.get_workspace_banner_overflow()).to_have_count(0)

    # Restore the viewport for any subsequent tests sharing this instance.
    page.set_viewport_size(original_size)
