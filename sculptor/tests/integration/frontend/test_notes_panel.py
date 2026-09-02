"""Integration tests for the Notes panel.

The Notes panel is a registered single-instance panel, opened on demand from the
section add-panel dropdown (the old Settings → Panels enable model is gone).
These tests cover opening it and that notes content is scoped per-workspace.
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import type_into_tiptap
from sculptor.testing.elements.notes_panel import get_notes_panel
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to open the Notes panel and write in its editor")
def test_open_notes_panel_renders_editor(sculptor_instance_: SculptorInstance) -> None:
    """Opening Notes from the add-panel dropdown renders its editor."""
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")

    notes = get_notes_panel(page)
    notes.open()
    expect(notes).to_be_visible()
    editor = notes.get_editor()
    expect(editor).to_be_visible()

    # The whole panel must be a click target, not just the first text line:
    # clicking well below the placeholder must begin editing (focus the
    # editor). Previously the contenteditable was only ~one line tall at the
    # top of the panel, so a real click lower down landed on non-editable
    # wrapper divs and did nothing. Assert focus (rather than typed text) so
    # the check is purely about where the click lands, independent of any
    # editor text-insertion path.
    panel_box = page.get_by_test_id(ElementIDs.NOTES_PANEL).bounding_box()
    assert panel_box is not None
    page.mouse.click(
        panel_box["x"] + panel_box["width"] / 2,
        panel_box["y"] + panel_box["height"] - 40,
    )
    expect(editor).to_be_focused()

    type_into_tiptap(page, editor, "a quick note")
    expect(editor).to_contain_text("a quick note")


@user_story("to jot notes in one workspace and have them stay scoped to that workspace")
def test_notes_content_is_scoped_per_workspace(sculptor_instance_: SculptorInstance) -> None:
    """Notes typed in one workspace should not appear in another workspace."""
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello", workspace_name="Notes-A")

    notes = get_notes_panel(page)
    notes.open()
    editor_a = notes.get_editor()
    expect(editor_a).to_be_visible()
    type_into_tiptap(page, editor_a, "workspace A note")
    expect(editor_a).to_contain_text("workspace A note")

    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello", workspace_name="Notes-B")
    notes.open()
    editor_b = notes.get_editor()
    expect(editor_b).to_be_visible()
    expect(editor_b).not_to_contain_text("workspace A note")
