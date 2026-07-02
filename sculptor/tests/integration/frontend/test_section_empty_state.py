"""Integration tests for the empty-section state and split close-from-empty.

An expanded section with no active panel shows a centered "Add panel" button plus
quick actions: always "New {recent} agent" and "New terminal", then up to three
most-recently-closed single-instance panels. Closing a single-instance panel records
it so it appears as a recently-closed quick action. An emptied split half keeps the
split and shows the same empty state; its "Close split" button is the only way a
split merges back (splits never auto-merge when a half empties).

Layouts are arranged by clicking the real UI (expand sections via the controls, open /
close panels via the ``+`` dropdown and tab close, split via the panel context menu).
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


@user_story("to see an add-panel button and quick actions in an empty section")
def test_empty_section_shows_add_button_and_quick_actions(sculptor_instance_: SculptorInstance) -> None:
    """An expanded, empty section shows the Add-panel button + New-agent / New-terminal actions."""
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Empty State WS")

    # The right section is collapsed by default; expanding it (no panels yet) shows the
    # empty state.
    right = PlaywrightWorkspaceSection(page, "right")
    right.expand_section()

    empty_state = PlaywrightEmptySectionState(page, "right")
    expect(empty_state.get_add_panel_button()).to_be_visible()
    expect(empty_state.get_quick_action("new-agent")).to_be_visible()
    expect(empty_state.get_quick_action("new-terminal")).to_be_visible()


@user_story("to re-open a recently-closed panel from the empty-section quick actions")
def test_recently_closed_panel_appears_in_quick_actions(sculptor_instance_: SculptorInstance) -> None:
    """Closing a single-instance panel surfaces it as a recently-closed quick action.

    Open Files in the right section, close it from its tab (a single-instance panel
    closes without a confirmation and is recorded as recently-closed), then the right
    section's empty state offers a "files" quick action to re-open it.
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Recent Closed WS")

    right = PlaywrightWorkspaceSection(page, "right")
    right.expand_section()
    open_panel(page, "files", "right")
    expect(right.get_panel_tab("files")).to_be_visible()

    # Close the Files panel from its tab (single-instance: no confirmation dialog).
    right_tabs = PlaywrightPanelTabElement(page, sub_section="right")
    right_tabs.get_tab_close_button("files").click()
    expect(right.get_panel_tab("files")).to_have_count(0)

    # The right section is empty again and offers a recently-closed "files" quick action.
    empty_state = PlaywrightEmptySectionState(page, "right")
    files_action = empty_state.get_quick_action("files")
    expect(files_action).to_be_visible()

    # Clicking it re-opens Files into the right section.
    files_action.click()
    expect(right.get_panel_tab("files")).to_be_visible()


@user_story("to close a split from an emptied half and reclaim the space")
def test_emptied_split_half_offers_close_split(sculptor_instance_: SculptorInstance) -> None:
    """An emptied split half shows the empty state with a Close-split button that merges back.

    Splitting the lone center agent into the secondary half empties the primary half,
    which then shows the empty state plus a "Close split" button; clicking it merges
    the split back into a single section.
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Close Split WS")
    center = PlaywrightWorkspaceSection(page, "center")
    agent_panel_id = center.get_active_tab().get_attribute("data-panel-id")
    assert agent_panel_id is not None

    # Split the agent into the secondary half -> the primary half is left empty.
    split = PlaywrightSectionSplit(page, "center")
    split.create_split(agent_panel_id, "vertical")
    split.assert_split_count(1)

    # The empty primary half shows the empty state with a Close-split button.
    primary_empty = PlaywrightEmptySectionState(page, "center")
    expect(primary_empty.get_close_split_button()).to_be_visible()

    # Closing the split merges back into one section that still holds the agent.
    split.close_split_from_empty_state("primary")
    split.assert_split_count(0)
    expect(center.get_panel_tab(agent_panel_id)).to_be_visible()
