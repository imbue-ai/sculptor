"""Integration tests for the split `+` button and its agent-type menu.

The chevron menu lists the agent types (pi gated behind multi-harness),
selecting Terminal creates a "Terminal N" agent, and a plain `+` click
creates the last-used type. Terminal-panel behavior is covered by the
terminal-agent tests; here we only assert tab titles.
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.terminal import get_agent_terminal_panel
from sculptor.testing.elements.user_config import disable_multi_harness
from sculptor.testing.elements.user_config import enable_multi_harness
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to create agents of different types from the tab bar")
def test_agent_type_menu_creates_terminal_agent_and_remembers_type(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Plain `+` keeps one-click Claude creation; the menu creates Terminal
    agents and updates the last-used type for subsequent plain clicks."""
    page = sculptor_instance_.page
    task_page = PlaywrightTaskPage(page=page)
    agent_tab_bar = task_page.get_agent_tab_bar()

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Agent Type WS")
    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(1)

    # Plain + click creates a Claude agent (initial last-used type): the new
    # tab is "Agent 2" and the chat panel is present.
    agent_tab_bar.get_add_agent_button().click()
    expect(agent_tabs).to_have_count(2)
    expect(agent_tab_bar.get_agent_tab_by_name("Agent 2")).to_have_count(1)
    expect(task_page.get_chat_panel()).to_be_visible()

    # Chevron menu → Terminal creates "Terminal 1" (numbered independently
    # from "Agent N") whose main panel is a terminal, not a chat.
    agent_tab_bar.open_agent_type_menu()
    agent_tab_bar.get_agent_type_menu_item_terminal().click()
    expect(agent_tabs).to_have_count(3)
    expect(agent_tab_bar.get_agent_tab_by_name("Terminal 1")).to_have_count(1)
    expect(get_agent_terminal_panel(page)).to_be_visible()
    expect(page.get_by_test_id(ElementIDs.CHAT_INPUT)).to_have_count(0)

    # Last-used type persisted: a plain + click now creates another Terminal.
    agent_tab_bar.get_add_agent_button().click()
    expect(agent_tabs).to_have_count(4)
    expect(agent_tab_bar.get_agent_tab_by_name("Terminal 2")).to_have_count(1)

    # Choosing Claude from the menu restores it as the last-used type (and
    # keeps the shared instance's default for subsequent tests).
    agent_tab_bar.open_agent_type_menu()
    agent_tab_bar.get_agent_type_menu_item_claude().click()
    expect(agent_tabs).to_have_count(5)
    expect(agent_tab_bar.get_agent_tab_by_name("Agent 3")).to_have_count(1)


@user_story("to only see the pi agent type when multi-harness is enabled")
def test_agent_type_menu_gates_pi_behind_multi_harness(
    sculptor_instance_: SculptorInstance,
) -> None:
    page = sculptor_instance_.page
    task_page = PlaywrightTaskPage(page=page)
    agent_tab_bar = task_page.get_agent_tab_bar()

    # The flag is sticky on the shared instance — reset it defensively.
    disable_multi_harness(page)
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Pi Gating WS")

    menu = agent_tab_bar.open_agent_type_menu()
    expect(agent_tab_bar.get_agent_type_menu_item_claude()).to_be_visible()
    expect(agent_tab_bar.get_agent_type_menu_item_terminal()).to_be_visible()
    expect(agent_tab_bar.get_agent_type_menu_item_pi()).to_have_count(0)
    page.keyboard.press("Escape")
    expect(menu).not_to_be_visible()

    try:
        enable_multi_harness(page)
        agent_tab_bar.open_agent_type_menu()
        expect(agent_tab_bar.get_agent_type_menu_item_pi()).to_be_visible()
        page.keyboard.press("Escape")
    finally:
        disable_multi_harness(page)


@user_story("to see registered terminal agents in the type menu without restarting")
def test_registered_terminal_agent_appears_in_menu_and_creates(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Dropping a registration TOML makes it appear on the next menu open
    (the backend re-reads the directory per request); creating it names the
    tab from display_name and opens a terminal panel."""
    page = sculptor_instance_.page
    task_page = PlaywrightTaskPage(page=page)
    agent_tab_bar = task_page.get_agent_tab_bar()

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Registered Agent WS")

    # The registration does not exist yet — the menu shows no registered entry.
    agent_tab_bar.open_agent_type_menu()
    expect(agent_tab_bar.get_agent_type_menu_item_registered("fake-reg")).to_have_count(0)
    page.keyboard.press("Escape")
    expect(agent_tab_bar.get_agent_type_menu()).not_to_be_visible()

    # Drop a registration file into the live instance's sculptor folder.
    registrations_dir = sculptor_instance_.sculptor_folder / "terminal_agents"
    registrations_dir.mkdir(parents=True, exist_ok=True)
    (registrations_dir / "fake-reg.toml").write_text(
        'display_name = "Fake Reg"\nlaunch_command = "echo hello-from-registration"\n'
    )
    try:
        # No restart: the entry appears on the next menu open.
        agent_tab_bar.open_agent_type_menu()
        registered_item = agent_tab_bar.get_agent_type_menu_item_registered("fake-reg")
        expect(registered_item).to_be_visible()
        registered_item.click()

        # Created agent is named from display_name and shows a terminal panel.
        expect(agent_tab_bar.get_agent_tab_by_name("Fake Reg 1")).to_have_count(1)
        expect(get_agent_terminal_panel(page)).to_be_visible()
        expect(page.get_by_test_id(ElementIDs.CHAT_INPUT)).to_have_count(0)
    finally:
        (registrations_dir / "fake-reg.toml").unlink(missing_ok=True)
