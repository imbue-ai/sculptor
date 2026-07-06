"""Add Workspace form's first-agent type picker.

Agent type is per-agent, so the form's picker chooses the type of the
workspace's *first agent* via createWorkspaceAgent. The select is always
visible and lists every agent type (Claude, Pi, Terminal).
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.add_panel_dropdown import PlaywrightAddPanelDropdownElement
from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
from sculptor.testing.elements.terminal import expect_terminal_panel_replaces_chat
from sculptor.testing.fake_pi import install_fake_pi_binary
from sculptor.testing.playwright_utils import open_new_workspace_form
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to see the first-agent type picker default to Claude on the Add Workspace form")
def test_agent_type_select_visible_with_claude_default(
    sculptor_instance_: SculptorInstance,
) -> None:
    page = sculptor_instance_.page

    open_new_workspace_form(page)
    picker = page.get_by_test_id(ElementIDs.ADD_WORKSPACE_AGENT_TYPE_SELECT)
    expect(picker).to_be_visible()
    expect(picker).to_contain_text("Claude")


@user_story("to always see the pi agent type in the Add Workspace form")
def test_pi_option_always_listed(
    sculptor_instance_: SculptorInstance,
) -> None:
    page = sculptor_instance_.page

    open_new_workspace_form(page)
    picker = page.get_by_test_id(ElementIDs.ADD_WORKSPACE_AGENT_TYPE_SELECT)
    picker.click()
    expect(page.get_by_test_id(ElementIDs.AGENT_TYPE_OPTION_CLAUDE)).to_be_visible()
    expect(page.get_by_test_id(ElementIDs.AGENT_TYPE_OPTION_TERMINAL)).to_be_visible()
    expect(page.get_by_test_id(ElementIDs.AGENT_TYPE_OPTION_PI)).to_be_visible()
    page.keyboard.press("Escape")


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
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")
    expect(panel_tabs.get_panel_tab_by_name("Terminal 1")).to_have_count(1)


@user_story("to have the new-workspace picker remember my last-used agent type")
def test_first_agent_type_defaults_to_shared_last_used(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Both creation surfaces share one MRU, but the pinned "New {recent} agent"
    row normalizes a remembered "terminal" to Claude: the add-panel model has no
    bare terminal AGENT (the dedicated "New terminal" row owns terminal
    creation), while the new-workspace form's picker legitimately offers
    Terminal and so reads the shared MRU un-normalized. A non-terminal type
    (pi) still surfaces on BOTH."""
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(
        sculptor_page=page,
        workspace_name="MRU Source WS",
        model_name=None,
        agent_type="terminal",
    )

    # The form's creation recorded the MRU as "terminal" (createWorkspace
    # optimistically sets lastUsedAgentType in userConfigAtom, and the backend
    # persists it on create). The pinned "New {recent} agent" row NORMALIZES
    # that to Claude — terminal creation is owned by the dedicated "New
    # terminal" row offered alongside it.
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")
    dropdown = PlaywrightAddPanelDropdownElement(page, sub_section="center")
    dropdown.open()
    new_agent_item = dropdown.get_new_agent_item()
    expect(new_agent_item).to_contain_text("New Claude agent")
    expect(dropdown.get_new_terminal_item()).to_be_visible()
    page.keyboard.press("Escape")

    # The FORM still reads the shared MRU un-normalized: the next new-workspace
    # form opens preset to Terminal. Checked BEFORE clicking the pinned row
    # below, because that click re-records the MRU as the type it creates
    # (Claude), which would overwrite the form's Terminal preset.
    open_new_workspace_form(page)
    picker = page.get_by_test_id(ElementIDs.ADD_WORKSPACE_AGENT_TYPE_SELECT)
    expect(picker).to_contain_text("Terminal")
    page.keyboard.press("Escape")
    expect(picker).to_have_count(0)

    # Clicking the pinned row acts on the NORMALIZED type too: it creates a
    # Claude agent ("Claude 1" — numbering is per type prefix), not "Terminal 2".
    dropdown.open()
    dropdown.get_new_agent_item().click()
    expect(panel_tabs.get_panel_tab_by_name("Claude 1")).to_have_count(1)
    expect(panel_tabs.get_panel_tab_by_name("Terminal 2")).to_have_count(0)

    # Only terminal is normalized — a NON-terminal MRU still flows through both
    # surfaces: a pi-first workspace makes the pinned row read "New pi agent"
    # AND presets the next new-workspace form to pi.
    install_fake_pi_binary(sculptor_instance_.fake_bin_dir)
    start_task_and_wait_for_ready(
        sculptor_page=page,
        workspace_name="MRU Pi WS",
        model_name=None,
        agent_type="pi",
    )
    dropdown.open()
    expect(dropdown.get_new_agent_item()).to_contain_text("New pi agent")
    page.keyboard.press("Escape")

    open_new_workspace_form(page)
    expect(picker).to_contain_text("pi")
