"""Integration tests for the section `+` add-panel dropdown (PANEL-01..06, 12, 15).

The dropdown is the single creation surface for agents, terminals, and single-instance
panels (co-owned with Sections). Its rows, in order: the pinned "New {recent} agent"
(with the new-agent keybinding shown), an agent-type sub-menu (Claude / pi-gated /
registered — NO bare "Terminal" type, Decision B2), "New terminal", then a separator
and every single-instance panel not currently open. New agents always land in CENTER
regardless of which section's `+` was used (PANEL-06). Cmd+K offers the same flow
(PANEL-12).

These cases are CREATE-not-migrate (per `03_07_agent_terminal_panel_tests.md`): they
absorb `test_agent_type_menu.py` (sub-menu + pi gating + registered-without-restart).
Task 8.2 deletes the superseded file.
"""

import re

from playwright.sync_api import expect

from sculptor.testing.elements.add_panel_dropdown import PlaywrightAddPanelDropdownElement
from sculptor.testing.elements.add_panel_dropdown import close_seeded_panel
from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
from sculptor.testing.elements.user_config import disable_pi_agent
from sculptor.testing.elements.user_config import enable_pi_agent
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to see the add-panel dropdown's creation rows in order")
def test_dropdown_shows_new_agent_terminal_and_panels(sculptor_instance_: SculptorInstance) -> None:
    """The center `+` dropdown shows New agent, the agent-type sub-menu, New terminal,
    and the single-instance panel options (PANEL-01..05)."""
    page = sculptor_instance_.page
    dropdown = PlaywrightAddPanelDropdownElement(page, sub_section="center")

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Add Dropdown WS")
    # Files is seeded open in the left section by default, so close it first to return it
    # to the single-instance re-add list.
    close_seeded_panel(page, "files")
    dropdown.open()

    expect(dropdown.get_new_agent_item()).to_be_visible()
    expect(dropdown.get_agent_type_submenu_trigger()).to_be_visible()
    expect(dropdown.get_new_terminal_item()).to_be_visible()
    # Files (now closed) appears in the single-instance re-add list.
    expect(dropdown.get_panel_option("files")).to_be_visible()


@user_story("to see the new-agent keybinding on the pinned recent-agent row")
def test_new_agent_row_shows_recent_type_and_shortcut(sculptor_instance_: SculptorInstance) -> None:
    """The pinned row names the recently-used agent type (Claude by default) and shows
    the new-agent keybinding (Cmd+Shift+T)."""
    page = sculptor_instance_.page
    dropdown = PlaywrightAddPanelDropdownElement(page, sub_section="center")

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Recent Pin WS")
    dropdown.open()

    new_agent = dropdown.get_new_agent_item()
    expect(new_agent).to_be_visible()
    expect(new_agent).to_contain_text("Claude")
    # The shortcut glyphs differ per platform (⌘⇧T vs Ctrl+Shift+T) but both end in
    # the new-agent key "T"; assert the trailing key is shown on the row.
    expect(new_agent).to_contain_text(re.compile(r"T$"))


@user_story("to choose Claude from the agent-type sub-menu without a bare Terminal type")
def test_agent_type_submenu_offers_claude_no_bare_terminal(sculptor_instance_: SculptorInstance) -> None:
    """The agent-type sub-menu offers Claude and omits the bare "Terminal" type (B2)."""
    page = sculptor_instance_.page
    dropdown = PlaywrightAddPanelDropdownElement(page, sub_section="center")

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Agent Type Submenu WS")
    dropdown.open()
    dropdown.open_agent_type_submenu()

    expect(dropdown.get_agent_type_item_claude()).to_be_visible()
    # No bare "Terminal" agent type (Decision B2): the old AGENT_TYPE_MENU_ITEM_TERMINAL
    # row is never rendered.
    expect(dropdown.get_agent_type_item_terminal()).to_have_count(0)


@user_story("to only see the pi agent type when pi-agent is enabled")
def test_agent_type_submenu_gates_pi(sculptor_instance_: SculptorInstance) -> None:
    """The pi agent type appears in the sub-menu only when pi-agent is enabled."""
    page = sculptor_instance_.page
    dropdown = PlaywrightAddPanelDropdownElement(page, sub_section="center")

    # The flag is sticky on the shared instance — reset it defensively.
    disable_pi_agent(page)
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Pi Gate Dropdown WS")

    dropdown.open()
    dropdown.open_agent_type_submenu()
    expect(dropdown.get_agent_type_item_claude()).to_be_visible()
    expect(dropdown.get_agent_type_item_pi()).to_have_count(0)
    page.keyboard.press("Escape")

    try:
        enable_pi_agent(page)
        dropdown.open()
        dropdown.open_agent_type_submenu()
        expect(dropdown.get_agent_type_item_pi()).to_be_visible()
        page.keyboard.press("Escape")
    finally:
        disable_pi_agent(page)


@user_story("to see a registered terminal agent in the sub-menu without restarting")
def test_registered_agent_appears_in_submenu_without_restart(sculptor_instance_: SculptorInstance) -> None:
    """A registration TOML dropped into the instance appears on the next sub-menu open
    (the backend re-reads the directory per request)."""
    page = sculptor_instance_.page
    dropdown = PlaywrightAddPanelDropdownElement(page, sub_section="center")

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Registered Submenu WS")

    # Not present yet.
    dropdown.open()
    dropdown.open_agent_type_submenu()
    expect(dropdown.get_agent_type_item_registered("fake-reg")).to_have_count(0)
    page.keyboard.press("Escape")

    registrations_dir = sculptor_instance_.sculptor_folder / "terminal_agents"
    registrations_dir.mkdir(parents=True, exist_ok=True)
    (registrations_dir / "fake-reg.toml").write_text(
        'display_name = "Fake Reg"\nlaunch_command = "echo hello-from-registration"\n'
    )
    try:
        dropdown.open()
        dropdown.open_agent_type_submenu()
        expect(dropdown.get_agent_type_item_registered("fake-reg")).to_be_visible()
        page.keyboard.press("Escape")
    finally:
        (registrations_dir / "fake-reg.toml").unlink(missing_ok=True)


@user_story("to create a new terminal from the add-panel dropdown")
def test_new_terminal_creates_terminal_panel(sculptor_instance_: SculptorInstance) -> None:
    """Selecting "New terminal" from the center `+` dropdown creates a terminal panel."""
    page = sculptor_instance_.page
    dropdown = PlaywrightAddPanelDropdownElement(page, sub_section="center")
    center_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="New Terminal Dropdown WS")

    dropdown.open()
    dropdown.get_new_terminal_item().click()

    # The center had one tab (the agent); the new terminal joins it. Terminal numbering
    # is workspace-global and the default layout already seeds a "Terminal 1" in the
    # bottom section, so the center terminal is the next free label rather than "Terminal 1".
    expect(center_tabs.get_panel_tabs()).to_have_count(2)
    expect(center_tabs.get_panel_tab_by_name("Terminal")).to_have_count(1)


@user_story("to not be offered a single-instance panel that is already open")
def test_open_single_instance_panel_drops_from_list(sculptor_instance_: SculptorInstance) -> None:
    """Opening Files removes it from the dropdown's single-instance re-add list (PANEL-15)."""
    page = sculptor_instance_.page
    dropdown = PlaywrightAddPanelDropdownElement(page, sub_section="center")

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Single Instance WS")
    # Files is seeded open in the left section by default; close it so it is offered in
    # the center dropdown's re-add list, then re-opening it drops it from the list again.
    close_seeded_panel(page, "files")

    dropdown.open()
    files_option = dropdown.get_panel_option("files")
    expect(files_option).to_be_visible()
    files_option.click()

    # Files is now open, so it is no longer offered in the re-add list.
    dropdown.open()
    expect(dropdown.get_panel_option("files")).to_have_count(0)


@user_story("to add an agent to the section whose add-panel button I used")
def test_new_agent_from_left_lands_in_left(sculptor_instance_: SculptorInstance) -> None:
    """A new agent created from the LEFT section `+` lands in the LEFT section, not center.

    Adding a panel from a section's `+` is an explicit, scoped action, so the agent joins
    THAT section (only the keyboard shortcut / CI-babysitter default to center). Expands
    the left section (Files is seeded there) and creates an agent from its `+`; the new
    agent tab appears in left and the center keeps just its original agent.
    """
    page = sculptor_instance_.page
    left_dropdown = PlaywrightAddPanelDropdownElement(page, sub_section="left")
    center_tabs = PlaywrightPanelTabElement(page, sub_section="center")
    left_tabs = PlaywrightPanelTabElement(page, sub_section="left")

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Section Targeting WS")
    expect(center_tabs.get_panel_tabs()).to_have_count(1)

    # Bring the left section up so its header `+` renders; Files is seeded there already.
    PlaywrightWorkspaceSection(page, "left").expand_section()
    expect(left_tabs.get_panel_tab("files")).to_be_visible()

    # Create an agent from the LEFT `+` — it lands in LEFT (joining the seeded
    # Files/Changes/Commits), not center.
    left_dropdown.open()
    left_dropdown.get_new_agent_item().click()
    # The new agent tab appears in the left section... (agent panel ids are dynamic,
    # so match the PANEL_TAB-agent:<id> testid by prefix via a get_by_test_id regex).
    expect(page.get_by_test_id("SECTION_HEADER-left").get_by_test_id(re.compile(r"^PANEL_TAB-agent:"))).to_have_count(
        1
    )
    # ...and NOT in center, which still shows only its original agent.
    expect(
        page.get_by_test_id("SECTION_HEADER-center").get_by_test_id(re.compile(r"^PANEL_TAB-agent:"))
    ).to_have_count(1)


@user_story("to add an agent to the right section without breaking the chat")
def test_add_agent_to_right_section_renders_both_chats(sculptor_instance_: SculptorInstance) -> None:
    """Adding an agent to the RIGHT section leaves a second agent chat mounted alongside
    the center one; both must render (regression for the single-StreamingEngine crash).

    Before the fix, mounting a second agent chat threw "StreamingEngine already
    registered. Only one stream may be active at a time." — so a right-section agent
    could never render while the center agent was open.
    """
    page = sculptor_instance_.page
    right_dropdown = PlaywrightAddPanelDropdownElement(page, sub_section="right")
    right_tabs = PlaywrightPanelTabElement(page, sub_section="right")
    center_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Add Agent Right WS")
    expect(center_tabs.get_panel_tabs()).to_have_count(1)

    # Expand the (empty) right section and add an agent from its `+`.
    PlaywrightWorkspaceSection(page, "right").expand_section()
    right_dropdown.open()
    right_dropdown.get_new_agent_item().click()

    # The new agent lands in the right section; the center keeps its own agent.
    expect(right_tabs.get_panel_tabs()).to_have_count(1)
    expect(center_tabs.get_panel_tabs()).to_have_count(1)

    # Both agent panels are mounted at once (one per section) and each runs its own
    # streaming engine, so both chat panels render rather than one crashing the engine.
    expect(page.get_by_test_id("CHAT_PANEL")).to_have_count(2)


@user_story("to add a panel through Cmd+K targeting the center section")
def test_cmd_k_add_panel_to_center(sculptor_instance_: SculptorInstance) -> None:
    """Cmd+K → Add panel → Center → New agent creates an agent in center (PANEL-12/06)."""
    page = sculptor_instance_.page
    task_page = PlaywrightTaskPage(page=page)
    center_tabs = PlaywrightPanelTabElement(page, sub_section="center")

    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="Cmd K Add Panel WS")
    expect(center_tabs.get_panel_tabs()).to_have_count(1)

    palette = task_page.open_command_palette_with_keyboard()
    palette.select_by_command_id("addpanel.open")
    palette.select_by_command_id("addpanel.location.center")
    palette.select_by_command_id("addpanel.panels.new_agent")

    expect(center_tabs.get_panel_tabs()).to_have_count(2)
