"""Round-trip stability regression for the workspace layout (PERSIST-04).

A round trip that reinitializes the Jotai layout atoms from localStorage must not drop
panels: the agent in the center and a user-added terminal both survive navigating away
and back. This guards the Home→back regression where atom re-hydration could lose the
active agent or a freshly-added panel.

The arrangement is built by clicking the real UI (expand the right section, add a
terminal there); ``navigate_away_and_back`` then forces the atoms to re-hydrate from
localStorage.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.add_panel_dropdown import create_terminal_panel
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.playwright_utils import navigate_away_and_back
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to keep my agent and added panels after navigating away and back")
def test_agent_and_added_panel_survive_round_trip(sculptor_instance_: SculptorInstance) -> None:
    """Expanding right + adding a terminal there survives an away-and-back round trip (PERSIST-04)."""
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Round Trip WS")

    center = PlaywrightWorkspaceSection(page, "center")
    agent_panel_id = center.get_active_tab().get_attribute("data-panel-id")
    assert agent_panel_id is not None and agent_panel_id.startswith("agent:")

    # Add a terminal into the (default-collapsed) right section.
    create_terminal_panel(page, "right")
    right = PlaywrightWorkspaceSection(page, "right")
    expect(right.get_panel_tabs()).to_have_count(1)
    right_terminal_id = right.get_active_tab().get_attribute("data-panel-id")
    assert right_terminal_id is not None and right_terminal_id.startswith("terminal:")

    # Force the layout atoms to re-hydrate from localStorage.
    navigate_away_and_back(page)

    # The agent (center) and the added terminal (right) both survive the round trip.
    expect(center.get_panel_tab(agent_panel_id)).to_be_visible()
    expect(PlaywrightWorkspaceSection(page, "right").get_panel_tab(right_terminal_id)).to_be_visible()
