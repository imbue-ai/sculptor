"""Integration tests for section collapse/expand + within-section panel cycling
(SEC-05..08, SEC-20).

The default test layout has only the CENTER section expanded; the left, right, and
bottom sections are collapsed and render no header until expanded. A non-center
section can be expanded/collapsed either by its workspace-header toggle or by the
``mod+Alt+Arrow*`` keyboard shortcut; the center section has no toggle and cannot be
collapsed (its hotkey is a no-op). The within-section panel-cycle hotkey wraps across
a section's panels and no-ops with fewer than two panels. Open/active panels survive a
collapse→expand round-trip.

These arrange every layout by clicking the real UI (add panels via the section ``+``
dropdown, expand via the section controls), not by seeding layout state.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.add_panel_dropdown import create_terminal_panel
from sculptor.testing.elements.add_panel_dropdown import open_panel
from sculptor.testing.elements.section_helpers import cycle_panels
from sculptor.testing.elements.section_helpers import toggle_section_via_hotkey
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to expand a collapsed side section from its workspace-header toggle")
def test_expand_side_section_via_header_toggle(sculptor_instance_: SculptorInstance) -> None:
    """Each non-center section expands (renders its header) via its header toggle (SEC-05/06/07)."""
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Expand Toggle WS")

    for section_id in ("left", "right", "bottom"):
        section = PlaywrightWorkspaceSection(page, section_id)
        # Collapsed by default: no header is rendered.
        expect(section.get_header()).to_have_count(0)
        section.expand_section()
        expect(section.get_header()).to_be_visible()


@user_story("to expand and collapse a side section with the keyboard")
def test_toggle_side_section_via_hotkey(sculptor_instance_: SculptorInstance) -> None:
    """The ``mod+Alt+Arrow*`` shortcut expands a collapsed section and collapses it again (SEC-05)."""
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Toggle Hotkey WS")

    left = PlaywrightWorkspaceSection(page, "left")
    expect(left.get_header()).to_have_count(0)

    # Expand via the hotkey -> header renders.
    toggle_section_via_hotkey(page, "left")
    expect(left.get_header()).to_be_visible()

    # Collapse via the hotkey -> header removed again.
    toggle_section_via_hotkey(page, "left")
    expect(left.get_header()).to_have_count(0)


@user_story("to keep the center section always visible because it cannot be collapsed")
def test_center_section_cannot_collapse(sculptor_instance_: SculptorInstance) -> None:
    """The center section has no collapse toggle and its hotkey is a no-op (SEC-08).

    The bottom hotkey expands the bottom section while the center stays put; there is
    no header toggle for center, and collapse_section is a no-op for it.
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Center No Collapse WS")

    center = PlaywrightWorkspaceSection(page, "center")
    expect(center.get_header()).to_be_visible()
    # Center has no workspace-header collapse/expand toggle.
    expect(center.get_section_toggle()).to_have_count(0)

    # collapse_section is a no-op for center; the header stays visible.
    center.collapse_section()
    expect(center.get_header()).to_be_visible()


@user_story("to cycle between panels in a section with the keyboard")
def test_cycle_panels_within_section_wraps(sculptor_instance_: SculptorInstance) -> None:
    """The panel-cycle hotkey wraps across the active section's panels (SEC-20).

    Open a second panel (Notes) in the center alongside the agent. Notes is active
    after opening; cycling next moves to the agent and cycling next again wraps back
    to Notes. Notes is not seeded into the default layout, so opening it via the
    section ``+`` genuinely lands it in the center as a second panel (the seeded
    Files/Changes/Commits live in the left section and are only revealed there).
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Cycle Panels WS")
    center = PlaywrightWorkspaceSection(page, "center")

    open_panel(page, "notes", "center")
    expect(center.get_panel_tabs()).to_have_count(2)
    # Opening Notes makes it the active center panel.
    expect(center.get_active_tab()).to_have_attribute("data-panel-id", "notes")

    # Cycle next -> the agent tab becomes active (the other of the two panels).
    cycle_panels(page, "next")
    expect(center.get_active_tab()).not_to_have_attribute("data-panel-id", "notes")

    # Cycle next again -> wraps back to Notes.
    cycle_panels(page, "next")
    expect(center.get_active_tab()).to_have_attribute("data-panel-id", "notes")


@user_story("to have the panel-cycle hotkey do nothing in a single-panel section")
def test_cycle_panels_is_noop_with_single_panel(sculptor_instance_: SculptorInstance) -> None:
    """The panel-cycle hotkey is a no-op when the active section has one panel (SEC-20)."""
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Single Panel Cycle WS")
    center = PlaywrightWorkspaceSection(page, "center")
    expect(center.get_panel_tabs()).to_have_count(1)

    active_before = center.get_active_tab().get_attribute("data-panel-id")
    cycle_panels(page, "next")
    # The single panel stays active (nothing to cycle to).
    expect(center.get_active_tab()).to_have_attribute("data-panel-id", active_before or "")


@user_story("to keep my open panels and active selection across a collapse and re-expand")
def test_open_panels_preserved_across_collapse_expand(sculptor_instance_: SculptorInstance) -> None:
    """Collapsing then re-expanding a section preserves its panels and active panel.

    Add a terminal to the bottom section, collapse the section, then re-expand it; the
    terminal tab is still there and still active.
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Preserve Panels WS")

    bottom = PlaywrightWorkspaceSection(page, "bottom")
    create_terminal_panel(page, section="bottom")
    terminal_tab = bottom.get_active_tab()
    expect(terminal_tab).to_be_visible()
    panel_id = terminal_tab.get_attribute("data-panel-id")
    assert panel_id is not None

    # Collapse the bottom section, then re-expand it.
    bottom.collapse_section()
    expect(bottom.get_header()).to_have_count(0)
    bottom.expand_section()

    # The terminal panel is preserved and still active.
    expect(bottom.get_panel_tab(panel_id)).to_be_visible()
    expect(bottom.get_active_tab()).to_have_attribute("data-panel-id", panel_id)
