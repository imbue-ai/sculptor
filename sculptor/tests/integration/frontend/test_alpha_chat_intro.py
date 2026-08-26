"""Integration test for alpha chat intro text.

Verifies that the intro text shows correct agent and workspace names,
and reacts to renames of both.  Also verifies that the intro text does
not overlap with the first user message.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.alpha_chat_view import get_intro_bottom_offset
from sculptor.testing.elements.alpha_chat_view import get_message_top_offset
from sculptor.testing.elements.alpha_chat_view import scroll_alpha_chat_to_top
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to see correct names in the alpha chat intro that update on rename")
def test_alpha_chat_intro_shows_names_and_reacts_to_renames(
    sculptor_instance_: SculptorInstance,
) -> None:
    """The intro text displays agent and workspace names and updates when either is renamed.

    Steps:
    1. Create a workspace
    2. Verify the intro shows the workspace name
    3. Rename the agent and verify the intro updates
    4. Rename the workspace and verify the intro updates
    """
    page = sculptor_instance_.page

    # Step 1: Create workspace.
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:text `{"text": "Hello"}`',
        workspace_name="My Workspace",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Step 2: Verify initial names in the alpha view.
    alpha_chat_view = get_alpha_chat_view(page)
    intro = alpha_chat_view.get_intro()
    expect(intro).to_be_visible()
    expect(intro).to_contain_text("My Workspace")

    # Step 3: Rename the agent (via its panel tab) and verify.
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")
    agent_tab = panel_tabs.get_panel_tabs().first
    panel_tabs.rename_tab_via_context_menu(agent_tab, "Renamed Agent")
    # Wait for the tab text to update (confirms the rename round-tripped through
    # the backend) before asserting the intro, which reads from a different atom.
    expect(agent_tab).to_contain_text("Renamed Agent")
    expect(intro).to_contain_text("Renamed Agent")

    # Step 4: Rename the workspace (via its sidebar row) and verify.
    sidebar = get_workspace_sidebar(page)
    workspace_row = sidebar.get_workspace_rows().first
    sidebar.rename_workspace_via_context_menu(workspace_row, "Updated Workspace")
    expect(sidebar.get_workspace_rows().first).to_contain_text("Updated Workspace")
    expect(intro).to_contain_text("Updated Workspace")


@user_story("to see the intro text fully above the first user message without overlap")
def test_intro_text_renders_above_first_message(sculptor_instance_: SculptorInstance) -> None:
    """The intro text must not overlap with the first user message.

    The intro is rendered in normal document flow above the absolutely-positioned
    virtual items.  The virtualizer's paddingStart must match the actual intro
    height so the first message starts below the intro block, not inside it.

    With the buggy fixed paddingStart (64 px), the first message is positioned
    at translateY(64 px) while the intro block is taller (~120 px), causing the
    message to overlap the bottom half of the intro text.
    """
    page = sculptor_instance_.page

    # Create a workspace WITHOUT an initial prompt so the chat starts empty.
    task_page = start_task_and_wait_for_ready(sculptor_page=page, prompt="")
    chat_panel = task_page.get_chat_panel()

    alpha_chat_view = get_alpha_chat_view(page)
    expect(alpha_chat_view).to_be_visible()

    # Verify the intro block is visible before any messages.
    intro = alpha_chat_view.get_intro()
    expect(intro).to_be_visible()

    # Send the very first message.
    send_chat_message(chat_panel, 'fake_claude:text `{"text": "Hello"}`')

    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Scroll to the very top so both the intro and the first message are
    # as close to the viewport origin as possible.
    scroll_alpha_chat_to_top(page)

    # Measure positions via helpers (evaluate calls live in the helper module,
    # not in the test, so the integration_test_page_evaluate ratchet is satisfied).
    intro_bottom = get_intro_bottom_offset(page)
    first_msg_top = get_message_top_offset(page, data_index=0)

    assert intro_bottom >= 0, "Could not locate the intro block or scroll container"
    assert first_msg_top >= 0, "Could not locate the first message or scroll container"

    assert first_msg_top >= intro_bottom, (
        f"First user message (top={first_msg_top:.0f}px) overlaps the intro text (bottom={intro_bottom:.0f}px). The first message must render below the intro block."
    )
