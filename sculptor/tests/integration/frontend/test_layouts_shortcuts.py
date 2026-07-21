"""Integration tests for the Layouts feature's keyboard shortcuts (SCU-1725).

Cover the two keyboard journeys the switcher tests don't: opening the switcher with
its global ⌘⇧L chord, and binding a per-layout "apply" shortcut inline on the save
form and firing it later to switch layouts. The chords are pressed with the platform's
primary modifier (``get_playwright_modifier_key``) so the same test drives Cmd on
macOS and Ctrl on Linux.

FakeClaude's default response is enough here — these tests exercise the layout UI, not
agent behavior.
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story
from sculptor.testing.utils import get_playwright_modifier_key


@user_story("to open the layouts switcher with its keyboard shortcut")
def test_open_layouts_shortcut_opens_switcher_and_escape_closes(sculptor_instance_: SculptorInstance) -> None:
    """⌘⇧L opens the Layouts switcher from a ready workspace; Escape closes it."""
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Open Layouts WS")

    mod_key = get_playwright_modifier_key()
    page.keyboard.press(f"{mod_key}+Shift+l")

    switcher = page.get_by_test_id(ElementIDs.LAYOUTS_SWITCHER_DIALOG)
    expect(switcher).to_be_visible()

    page.keyboard.press("Escape")
    expect(switcher).to_be_hidden()


@user_story("to apply a saved layout with a keyboard shortcut I recorded")
def test_recorded_shortcut_applies_its_layout(sculptor_instance_: SculptorInstance) -> None:
    """Recording an inline shortcut when saving a layout binds that chord to it; pressing
    the chord later re-applies the layout even after a different one became current."""
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Shortcut Apply WS")
    sidebar = get_workspace_sidebar(page)

    mod_key = get_playwright_modifier_key()
    # ⌘⇧G / Ctrl+Shift+G is free of every static keybinding and can't collide.
    chord = f"{mod_key}+Shift+g"

    # Save "Alpha" with an inline shortcut, then "Bravo" (which becomes the current one).
    save_dialog = sidebar.open_layouts_switcher().open_save_dialog()
    save_dialog.record_shortcut(chord)
    save_dialog.save("Alpha")

    sidebar.open_layouts_switcher().open_save_dialog().save("Bravo")

    # Bravo is current and Alpha is not; Alpha's row carries the recorded shortcut hint,
    # which gates us on the binding being registered before we fire it.
    switcher = sidebar.open_layouts_switcher()
    expect(switcher.get_current_row()).to_contain_text("Bravo")
    expect(switcher.get_current_row()).not_to_contain_text("Alpha")
    expect(switcher.get_row_shortcut_hint("Alpha")).to_be_visible()

    # Close the switcher so no dismissible overlay guards the dispatcher, then press it.
    page.keyboard.press("Escape")
    expect(page.get_by_test_id(ElementIDs.LAYOUTS_SWITCHER_DIALOG)).to_be_hidden()
    page.keyboard.press(chord)

    # The per-layout dispatcher applied Alpha: it is now the workspace's current layout.
    switcher = sidebar.open_layouts_switcher()
    expect(switcher.get_current_row()).to_contain_text("Alpha")
