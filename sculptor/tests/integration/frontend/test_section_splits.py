"""Integration tests for section splits (SPLIT-01, SPLIT-02, SPLIT-03).

A panel is split off into a new SECONDARY sub-section by right-clicking its tab and
choosing "Create {direction} split and move panel". The allowed directions are
per-section: left/right sections allow only a bottom (horizontal) split, the bottom
section allows only a right (vertical) split, and the center allows both. A section
holds at most one split, so the create-split options vanish once a split exists.
A split persists when a half empties: the emptied half shows the empty-section
state (never an auto-merge) until the split is closed explicitly from that state.
(SPLIT-06 — a maximized split shows one sub-section — lives in
``test_section_active_and_maximize.py``.)

Layouts are arranged by clicking the real UI (add panels via the ``+`` dropdown, split
via the panel context menu).
"""

from playwright.sync_api import expect

from sculptor.testing.elements.add_panel_dropdown import open_panel
from sculptor.testing.elements.panel_empty_state import PlaywrightEmptySectionState
from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
from sculptor.testing.elements.section_split import PlaywrightSectionSplit
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# Splits move a NOTES panel (not the agent) into the secondary half: rendering two agent
# chat panels at once exceeds the single active-stream limit (the deferred AGENT-03/05
# concurrent-rendering work), which is orthogonal to the split behaviour under test here.
# Notes is a single-instance panel that is NOT seeded into the default layout, so opening
# it via the section ``+`` genuinely lands it in the requested section (the seeded
# Files/Changes/Commits live in the left section and ``open_panel`` only reveals them
# there — it never moves them into center).


@user_story("to split a center panel into a side-by-side pair")
def test_create_right_split_moves_panel_to_secondary(sculptor_instance_: SculptorInstance) -> None:
    """A center "Create right split" moves the panel into a new secondary half (SPLIT-01/02).

    Open a Notes panel in the center, then split it off with the vertical (right) split:
    it leaves the primary half and appears in the secondary half.
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Right Split WS")
    center = PlaywrightWorkspaceSection(page, "center")

    open_panel(page, "notes", "center")
    expect(center.get_panel_tab("notes")).to_be_visible()

    split = PlaywrightSectionSplit(page, "center")
    split.create_split("notes", "vertical")
    split.assert_split_count(1)

    # The panel now lives in the secondary half and not in the primary half.
    secondary = split.get_subsection("secondary")
    primary = split.get_subsection("primary")
    expect(secondary.get_panel_tab("notes")).to_be_visible()
    expect(primary.get_panel_tab("notes")).to_have_count(0)


@user_story("to split a center panel into a stacked pair")
def test_create_bottom_split_moves_panel_to_secondary(sculptor_instance_: SculptorInstance) -> None:
    """A center "Create bottom split" (horizontal) moves the panel into the secondary half (SPLIT-01/02)."""
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Bottom Split WS")
    center = PlaywrightWorkspaceSection(page, "center")

    open_panel(page, "notes", "center")
    expect(center.get_panel_tab("notes")).to_be_visible()

    split = PlaywrightSectionSplit(page, "center")
    split.create_split("notes", "horizontal")
    split.assert_split_count(1)

    secondary = split.get_subsection("secondary")
    expect(secondary.get_panel_tab("notes")).to_be_visible()


@user_story("to be offered only the split directions a section allows")
def test_center_offers_both_split_directions(sculptor_instance_: SculptorInstance) -> None:
    """The center section's panel context menu offers BOTH split directions (SPLIT-02)."""
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Center Dirs WS")

    split = PlaywrightSectionSplit(page, "center")
    split.assert_directions_available(("horizontal", "vertical"))


@user_story("to only split a side section along its allowed direction")
def test_right_section_offers_only_bottom_split(sculptor_instance_: SculptorInstance) -> None:
    """The right section's panel context menu offers only the bottom (horizontal) split (SPLIT-02)."""
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Right Dirs WS")

    # Put a panel in the right section so its tab can be right-clicked.
    right = PlaywrightWorkspaceSection(page, "right")
    right.expand_section()
    open_panel(page, "files", "right")
    expect(right.get_panel_tab("files")).to_be_visible()

    split = PlaywrightSectionSplit(page, "right")
    split.assert_directions_available(("horizontal",))


@user_story("to only split the bottom section along its allowed direction")
def test_bottom_section_offers_only_right_split(sculptor_instance_: SculptorInstance) -> None:
    """The bottom section's panel context menu offers only the right (vertical) split (SPLIT-02)."""
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Bottom Dirs WS")

    bottom = PlaywrightWorkspaceSection(page, "bottom")
    bottom.expand_section()
    open_panel(page, "files", "bottom")
    expect(bottom.get_panel_tab("files")).to_be_visible()

    split = PlaywrightSectionSplit(page, "bottom")
    split.assert_directions_available(("vertical",))


@user_story("to be limited to a single split per section")
def test_one_split_max_removes_create_options(sculptor_instance_: SculptorInstance) -> None:
    """After a section is split once, the create-split options disappear (SPLIT-03).

    Split a center panel, then re-open a panel tab's context menu in the now-split
    section: neither create-split option is offered (one-split-max).
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="One Split Max WS")
    center = PlaywrightWorkspaceSection(page, "center")

    open_panel(page, "notes", "center")
    expect(center.get_panel_tab("notes")).to_be_visible()

    split = PlaywrightSectionSplit(page, "center")
    split.create_split("notes", "vertical")
    split.assert_split_count(1)

    # Re-opening a tab's context menu (in the still-populated primary half) offers no
    # create-split options now that the section is split.
    split.assert_directions_available(())


@user_story("to keep a split after closing its last panel and refill the empty half in place")
def test_split_persists_after_closing_last_panel_and_refills_in_place(sculptor_instance_: SculptorInstance) -> None:
    """Closing the secondary half's last panel keeps the split; a quick action refills that half.

    Split a Notes panel into the center secondary half, then close it from its tab:
    the split persists and the emptied half shows the empty state instead of merging
    back. The empty state's recently-closed "notes" quick action then re-opens Notes
    into that same half, leaving the primary half untouched.
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Split Persists WS")
    center = PlaywrightWorkspaceSection(page, "center")
    agent_panel_id = center.get_active_tab().get_attribute("data-panel-id")
    assert agent_panel_id is not None

    open_panel(page, "notes", "center")
    expect(center.get_panel_tab("notes")).to_be_visible()

    split = PlaywrightSectionSplit(page, "center")
    split.create_split("notes", "vertical")
    split.assert_split_count(1)

    # Close the split-off panel from its tab (single-instance: closes silently and is
    # recorded as recently-closed). The secondary half empties but the split stays.
    secondary = split.get_subsection("secondary")
    secondary_tabs = PlaywrightPanelTabElement(page, sub_section="center:secondary")
    secondary_tabs.get_tab_close_button("notes").click()
    expect(secondary.get_panel_tab("notes")).to_have_count(0)
    split.assert_split_count(1)

    # The emptied half shows the empty state, including its close-split affordance.
    empty_state = PlaywrightEmptySectionState(page, "center:secondary")
    expect(empty_state.get_add_panel_button()).to_be_visible()
    expect(empty_state.get_close_split_button()).to_be_visible()

    # The recently-closed "notes" quick action re-opens Notes into the SAME half.
    notes_action = empty_state.get_quick_action("notes")
    expect(notes_action).to_be_visible()
    notes_action.click()
    expect(secondary.get_panel_tab("notes")).to_be_visible()
    split.assert_split_count(1)

    # The primary half is untouched: the agent still lives there.
    expect(split.get_subsection("primary").get_panel_tab(agent_panel_id)).to_be_visible()
