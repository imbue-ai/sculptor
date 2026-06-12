"""Integration test for routing prompt features to capable terminal agents.

A fake registered program opts into automated prompts, signals idle, and
echoes stdin lines. With it at its prompt, the Commit button must send the
commit prompt through the terminal-input endpoint (visible as typed input in
the terminal buffer); once the program signals busy the button disables.
Plain terminals and non-opt-in registrations stay disabled (phase-1
behavior), and chat agents in the same workspace keep sending chat messages.
"""

import re

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.agent_tab import PlaywrightAgentTabBarElement
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.terminal import wait_for_xterm_substring
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

_WRITE_FILE_PROMPT = """\
fake_claude:write_file `{
  "file_path": "hello.py",
  "content": "print('hello')\\n"
}`"""

# Idle at start (at its prompt), echo each received line, go busy after the
# first one — mirroring a real TUI's prompt-submit lifecycle. The IDLE-DONE
# marker prints only after `sculpt signal idle` returns (the POST completed):
# the endpoint 409s a no-signals-yet agent, and the neutral tab dot cannot
# distinguish that state, so the test gates on the marker. The marker is
# assembled via printf so the ECHOED COMMAND LINE never contains it — a
# plain `echo IDLE-DONE` would match the xterm wait on the command echo,
# before the signal lands. No quotes or backslashes: the command is embedded
# in a TOML basic string.
_FAKE_PROMPTS_COMMAND = (
    "echo FAKE-PROMPTS-BANNER; sculpt signal idle; printf %sDONE IDLE-; echo; "
    + "while read -r _line; do echo RECEIVED:$_line; sculpt signal busy; done"
)
_NO_OPT_IN_COMMAND = "echo NO-OPT-IN-BANNER; sculpt signal idle; printf %sDONE NOPROMPT-; echo; read -r _line"

_NEUTRAL_DOT = re.compile(r"^(read|unread)$")


@user_story("to have Sculptor's prompt features reach a capable terminal agent")
def test_prompt_features_route_to_capable_terminal_agent(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page

    # A chat agent writes a file so the workspace has one uncommitted change —
    # the Commit button needs a non-zero change count regardless of agent type.
    task_page = start_task_and_wait_for_ready(page, prompt=_WRITE_FILE_PROMPT, workspace_name="Automated Prompts WS")
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    registrations_dir = sculptor_instance_.sculptor_folder / "terminal_agents"
    registrations_dir.mkdir(parents=True, exist_ok=True)
    (registrations_dir / "fake-prompts.toml").write_text(
        f'display_name = "Fake Prompts"\nlaunch_command = "{_FAKE_PROMPTS_COMMAND}"\naccepts_automated_prompts = true\n'
    )
    (registrations_dir / "fake-noprompt.toml").write_text(
        f'display_name = "No Prompt"\nlaunch_command = "{_NO_OPT_IN_COMMAND}"\n'
    )
    try:
        agent_tab_bar = PlaywrightAgentTabBarElement(page)
        agent_tab_bar.open_agent_type_menu()
        registered_item = agent_tab_bar.get_agent_type_menu_item_registered("fake-prompts")
        expect(registered_item).to_be_visible()
        registered_item.click()

        prompts_tab = agent_tab_bar.get_agent_tab_by_name("Fake Prompts 1").first
        expect(prompts_tab).to_be_visible()
        expect(page.get_by_test_id(ElementIDs.AGENT_TERMINAL_PANEL)).to_be_visible()
        wait_for_xterm_substring(page, "FAKE-PROMPTS-BANNER")
        # The idle signal landed in the backend: the program is at its prompt.
        wait_for_xterm_substring(page, "IDLE-DONE")
        expect(prompts_tab).to_have_attribute("data-dot-status", _NEUTRAL_DOT, timeout=15_000)

        task_page.activate_changes_panel(scope="uncommitted")
        commit_button = task_page.get_commit_button()
        expect(commit_button).to_be_visible()
        expect(commit_button).to_be_enabled()

        # The commit prompt arrives as typed input in the terminal.
        commit_button.click()
        wait_for_xterm_substring(page, "RECEIVED:Stage every changed")

        # The program signalled busy after the prompt — the button disables.
        expect(prompts_tab).to_have_attribute("data-dot-status", "running", timeout=15_000)
        expect(commit_button).to_be_disabled()

        # A registered agent WITHOUT the opt-in: disabled even when idle.
        agent_tab_bar.open_agent_type_menu()
        no_opt_in_item = agent_tab_bar.get_agent_type_menu_item_registered("fake-noprompt")
        expect(no_opt_in_item).to_be_visible()
        no_opt_in_item.click()
        no_opt_in_tab = agent_tab_bar.get_agent_tab_by_name("No Prompt 1").first
        expect(no_opt_in_tab).to_be_visible()
        wait_for_xterm_substring(page, "NOPROMPT-DONE")
        expect(no_opt_in_tab).to_have_attribute("data-dot-status", _NEUTRAL_DOT, timeout=15_000)
        expect(commit_button).to_be_disabled()

        # A plain terminal: disabled (phase-1 regression check).
        agent_tab_bar.open_agent_type_menu()
        agent_tab_bar.get_agent_type_menu_item_terminal().click()
        terminal_tab = agent_tab_bar.get_agent_tab_by_name("Terminal 1").first
        expect(terminal_tab).to_be_visible()
        expect(page.get_by_test_id(ElementIDs.AGENT_TERMINAL_PANEL)).to_be_visible()
        expect(commit_button).to_be_disabled()

        # Back on the chat agent the button sends a chat message as before.
        chat_tab = agent_tab_bar.get_agent_tab_by_name("Agent 1").first
        expect(chat_tab).to_be_visible()
        chat_tab.click()
        expect(commit_button).to_be_enabled()
        commit_button.click()
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)
    finally:
        (registrations_dir / "fake-prompts.toml").unlink(missing_ok=True)
        (registrations_dir / "fake-noprompt.toml").unlink(missing_ok=True)
