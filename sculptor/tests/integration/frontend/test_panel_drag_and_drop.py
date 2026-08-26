"""Smoke test for panel drag-and-drop via the KeyboardSensor.

This proves the keyboard-driven drag pipeline end-to-end before the rest of the
Phase-4 drag coverage is built on top of it. Dragging a panel from one section into
another is driven through the section drag handle + arrow keys (section_helpers).
"""

from playwright.sync_api import expect

from sculptor.testing.elements.add_panel_dropdown import open_panel
from sculptor.testing.elements.section_helpers import drag_panel_to_section
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to drag a panel from one section into another")
def test_drag_panel_from_center_to_right(sculptor_instance_: SculptorInstance) -> None:
    """A panel dragged from center to the right section moves there."""
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="DnD Smoke WS")

    # Bring Notes into the center section, then expand the right section so it renders a
    # drop target. Notes is a single-instance panel not seeded into the default layout,
    # so opening it via the section ``+`` genuinely lands it in the center (the seeded
    # Files/Changes/Commits live in the left section and are only revealed there).
    open_panel(page, "notes", "center")
    center = PlaywrightWorkspaceSection(page, "center")
    expect(center.get_panel_tab("notes")).to_be_visible()

    PlaywrightWorkspaceSection(page, "right").expand_section()

    drag_panel_to_section(page, "notes", "center", "right", "right")

    right = PlaywrightWorkspaceSection(page, "right")
    expect(right.get_panel_tab("notes")).to_be_visible()
    expect(center.get_panel_tab("notes")).to_have_count(0)


@user_story("to drop a panel onto a collapsed section to expand it")
def test_drag_panel_to_collapsed_section_expands(sculptor_instance_: SculptorInstance) -> None:
    """Dragging a panel onto a collapsed section's drop rail expands it."""
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="DnD Collapsed WS")

    # Notes is not seeded into the default layout, so opening it via the section ``+``
    # genuinely lands it in the center (the seeded Files/Changes/Commits stay in left).
    open_panel(page, "notes", "center")
    center = PlaywrightWorkspaceSection(page, "center")
    expect(center.get_panel_tab("notes")).to_be_visible()

    # The bottom section is collapsed by default; dropping onto its drop rail (which
    # only appears mid-drag) expands the section and lands the panel there.
    bottom = PlaywrightWorkspaceSection(page, "bottom")
    expect(bottom.get_header()).to_have_count(0)

    drag_panel_to_section(page, "notes", "center", "bottom", "down")

    expect(bottom.get_header()).to_be_visible()
    expect(bottom.get_panel_tab("notes")).to_be_visible()
    expect(center.get_panel_tab("notes")).to_have_count(0)
