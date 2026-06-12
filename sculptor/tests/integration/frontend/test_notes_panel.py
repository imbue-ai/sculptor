"""Integration tests for the Notes panel.

The Notes panel is registered in the workspace registry but ships
disabled by default (`defaultEnabled: false`). Users opt in via
Settings → Panels. These tests cover that opt-in flow and that notes
content is scoped per-workspace.
"""

from collections.abc import Iterator

import pytest
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.base import type_into_tiptap
from sculptor.testing.elements.notes_panel import get_notes_panel
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _set_notes_panel_enabled(page: Page, enabled: bool) -> None:
    """Toggle the Notes panel via Settings → Panels (idempotent)."""
    settings_page = navigate_to_settings_page(page=page)
    panels = settings_page.click_on_panels()
    panels.set_panel_enabled("notes", enabled)


@pytest.fixture(autouse=True)
def _reset_notes_panel(sculptor_instance_: SculptorInstance) -> Iterator[None]:
    """Disable the Notes panel after each test.

    The enabled state lives in localStorage and is shared across tests in
    the same instance, so a leaked `notes: true` would change the default
    behaviour for the next test.
    """
    yield
    _set_notes_panel_enabled(sculptor_instance_.page, enabled=False)


@user_story("to enable the Notes panel from the Panels settings page and see it in the workspace sidebar")
def test_enable_notes_panel_reveals_icon_and_renders_editor(sculptor_instance_: SculptorInstance) -> None:
    """Enabling Notes from Settings → Panels should reveal the sidebar icon
    and let the user open the editor."""
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")

    _set_notes_panel_enabled(page, enabled=True)
    page.go_back()

    notes = get_notes_panel(page)
    notes.open()
    expect(notes).to_be_visible()


@user_story("to jot notes in one workspace and have them stay scoped to that workspace")
def test_notes_content_is_scoped_per_workspace(sculptor_instance_: SculptorInstance) -> None:
    """Notes typed in one workspace should not appear in another workspace."""
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello", workspace_name="Notes-A")

    _set_notes_panel_enabled(page, enabled=True)
    page.go_back()

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
