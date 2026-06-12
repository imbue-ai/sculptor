"""Add Workspace form's first-agent type picker.

Replaces the old workspace-harness picker tests: agent type is per-agent,
so the form's picker chooses the type of the workspace's *first agent* via
createWorkspaceAgent. The select is always visible (Terminal is available to
everyone); only the pi option is gated behind the experimental multi-harness
flag.
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.agent_tab import PlaywrightAgentTabBarElement
from sculptor.testing.elements.terminal import expect_terminal_panel_replaces_chat
from sculptor.testing.elements.user_config import disable_multi_harness
from sculptor.testing.elements.user_config import enable_multi_harness
from sculptor.testing.playwright_utils import navigate_to_add_workspace_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to see the first-agent type picker default to Claude on the Add Workspace form")
def test_agent_type_select_visible_with_claude_default(
    sculptor_instance_: SculptorInstance,
) -> None:
    page = sculptor_instance_.page

    # The picker is no longer flag-gated — visible for everyone.
    disable_multi_harness(page)
    navigate_to_add_workspace_page(page)
    picker = page.get_by_test_id(ElementIDs.ADD_WORKSPACE_AGENT_TYPE_SELECT)
    expect(picker).to_be_visible()
    expect(picker).to_contain_text("Claude")


@user_story("to only see the pi agent type in the form when multi-harness is enabled")
def test_pi_option_gated_behind_multi_harness(
    sculptor_instance_: SculptorInstance,
) -> None:
    page = sculptor_instance_.page

    # The flag is sticky on the shared instance — reset it defensively.
    disable_multi_harness(page)
    navigate_to_add_workspace_page(page)
    picker = page.get_by_test_id(ElementIDs.ADD_WORKSPACE_AGENT_TYPE_SELECT)
    picker.click()
    expect(page.get_by_test_id(ElementIDs.AGENT_TYPE_OPTION_CLAUDE)).to_be_visible()
    expect(page.get_by_test_id(ElementIDs.AGENT_TYPE_OPTION_TERMINAL)).to_be_visible()
    expect(page.get_by_test_id(ElementIDs.AGENT_TYPE_OPTION_PI)).to_have_count(0)
    page.keyboard.press("Escape")

    try:
        enable_multi_harness(page)
        navigate_to_add_workspace_page(page)
        picker.click()
        expect(page.get_by_test_id(ElementIDs.AGENT_TYPE_OPTION_PI)).to_be_visible()
        page.keyboard.press("Escape")
    finally:
        disable_multi_harness(page)


@user_story("to start a workspace whose first agent is a Terminal agent")
def test_terminal_first_agent(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Selecting Terminal in the form creates a 'Terminal 1' first agent whose
    main panel is a terminal, not a chat."""
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(
        sculptor_page=page,
        workspace_name="Terminal First Agent WS",
        model_name=None,
        agent_type="terminal",
    )

    expect_terminal_panel_replaces_chat(page)
    expect(PlaywrightAgentTabBarElement(page).get_agent_tab_by_name("Terminal 1")).to_have_count(1)
