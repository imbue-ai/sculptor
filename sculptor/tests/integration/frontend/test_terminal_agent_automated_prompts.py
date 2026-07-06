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

from sculptor.testing.elements.action_dialog import get_action_dialog
from sculptor.testing.elements.add_panel_dropdown import PlaywrightAddPanelDropdownElement
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
from sculptor.testing.elements.terminal import get_agent_terminal_panel
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
        panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")
        dropdown = PlaywrightAddPanelDropdownElement(page, sub_section="center")
        dropdown.open()
        dropdown.open_agent_type_submenu()
        registered_item = dropdown.get_agent_type_item_registered("fake-prompts")
        expect(registered_item).to_be_visible()
        registered_item.click()

        prompts_tab = panel_tabs.get_panel_tab_by_name("Fake Prompts 1").first
        expect(prompts_tab).to_be_visible()
        expect(get_agent_terminal_panel(page)).to_be_visible()
        wait_for_xterm_substring(page, "FAKE-PROMPTS-BANNER")
        # The idle signal landed in the backend: the program is at its prompt.
        wait_for_xterm_substring(page, "IDLE-DONE")
        expect(prompts_tab).to_have_attribute("data-dot-status", _NEUTRAL_DOT)

        task_page.activate_changes_panel(scope="uncommitted")
        commit_button = task_page.get_commit_button()
        expect(commit_button).to_be_visible()
        expect(commit_button).to_be_enabled()

        # The commit prompt arrives as typed input in the terminal.
        commit_button.click()
        wait_for_xterm_substring(page, "RECEIVED:Stage every changed")

        # The program signalled busy after the prompt — the button disables.
        expect(prompts_tab).to_have_attribute("data-dot-status", "running")
        expect(commit_button).to_be_disabled()

        # A registered agent WITHOUT the opt-in: disabled even when idle.
        dropdown.open()
        dropdown.open_agent_type_submenu()
        no_opt_in_item = dropdown.get_agent_type_item_registered("fake-noprompt")
        expect(no_opt_in_item).to_be_visible()
        no_opt_in_item.click()
        no_opt_in_tab = panel_tabs.get_panel_tab_by_name("No Prompt 1").first
        expect(no_opt_in_tab).to_be_visible()
        wait_for_xterm_substring(page, "NOPROMPT-DONE")
        expect(no_opt_in_tab).to_have_attribute("data-dot-status", _NEUTRAL_DOT)
        expect(commit_button).to_be_disabled()

        # Back on the chat agent the button sends a chat message as before.
        chat_tab = panel_tabs.get_panel_tab_by_name("Claude 1").first
        expect(chat_tab).to_be_visible()
        chat_tab.click()
        expect(commit_button).to_be_enabled()
        commit_button.click()
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)
    finally:
        (registrations_dir / "fake-prompts.toml").unlink(missing_ok=True)
        (registrations_dir / "fake-noprompt.toml").unlink(missing_ok=True)


@user_story("to draft a non-auto-send action into a capable terminal agent without submitting it")
def test_non_auto_send_action_drafts_into_terminal_without_submitting(sculptor_instance_: SculptorInstance) -> None:
    """A non-auto-submit ("draft") action must insert its text into a capable
    terminal agent's PTY *without* submitting it — mirroring how the same action
    populates a rich-chat composer for the user to edit/send. Before the fix,
    terminal agents registered only ``sendMessage`` and left ``appendText`` null,
    so clicking a draft action was a silent no-op.

    Proof strategy: a draft insert (``submit=false``) writes a bracketed-paste
    body with no trailing Enter, so the program's ``read`` stays blocked and the
    drafted text sits in the line buffer (echoed, but unsubmitted). A later
    auto-submit action sends the Enter, completing that same line — so the
    program receives BOTH prompts concatenated in a single ``RECEIVED:`` line.
    That single line proves the draft was inserted (it is present) AND that it
    was not submitted on its own (it only surfaced once the second action sent
    the Enter). With the bug present, the draft never reaches the PTY, so only
    the second prompt appears.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        page, prompt="Draft action terminal test", workspace_name="Draft Action WS"
    )

    registrations_dir = sculptor_instance_.sculptor_folder / "terminal_agents"
    registrations_dir.mkdir(parents=True, exist_ok=True)
    (registrations_dir / "fake-prompts.toml").write_text(
        f'display_name = "Fake Prompts"\nlaunch_command = "{_FAKE_PROMPTS_COMMAND}"\naccepts_automated_prompts = true\n'
    )
    try:
        # Create a draft action (auto-submit OFF) and an auto-submit action.
        # No spaces in the prompts so they land on a single xterm line and the
        # concatenated RECEIVED line is matched exactly.
        actions_panel = task_page.get_actions_panel()
        actions_panel.get_add_button().click()
        draft_dialog = get_action_dialog(page)
        expect(draft_dialog).to_be_visible()
        draft_dialog.fill_name("Draft Insert")
        draft_dialog.fill_prompt("DRAFT-INSERT-PART")
        # The auto-submit switch defaults ON; toggle it OFF so the chip drafts.
        draft_dialog.get_auto_submit_switch().click()
        draft_dialog.click_save()
        expect(draft_dialog).not_to_be_visible()

        actions_panel.get_add_button().click()
        send_dialog = get_action_dialog(page)
        expect(send_dialog).to_be_visible()
        send_dialog.fill_name("Send Now")
        send_dialog.fill_prompt("SEND-NOW-PART")
        send_dialog.click_save()  # auto-submit stays ON
        expect(send_dialog).not_to_be_visible()

        # Launch the capable terminal agent and wait until it is at its prompt.
        panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")
        dropdown = PlaywrightAddPanelDropdownElement(page, sub_section="center")
        dropdown.open()
        dropdown.open_agent_type_submenu()
        registered_item = dropdown.get_agent_type_item_registered("fake-prompts")
        expect(registered_item).to_be_visible()
        registered_item.click()
        prompts_tab = panel_tabs.get_panel_tab_by_name("Fake Prompts 1").first
        expect(prompts_tab).to_be_visible()
        expect(get_agent_terminal_panel(page)).to_be_visible()
        wait_for_xterm_substring(page, "FAKE-PROMPTS-BANNER")
        wait_for_xterm_substring(page, "IDLE-DONE")
        expect(prompts_tab).to_have_attribute("data-dot-status", _NEUTRAL_DOT)

        # Click the DRAFT action: its text must reach the PTY (visible via the
        # line-discipline echo) WITHOUT being submitted. The echo is both the
        # core regression assertion (a null appendText writes nothing) and the
        # sync point that the write landed before the submit below.
        actions_panel = task_page.get_actions_panel()
        draft_chip = actions_panel.get_action_chip_by_name("Draft Insert")
        expect(draft_chip).to_be_enabled()
        draft_chip.click()
        wait_for_xterm_substring(page, "DRAFT-INSERT-PART")

        # A draft does not submit: no line was read, so the program never went
        # busy and the tab dot stays neutral.
        expect(prompts_tab).to_have_attribute("data-dot-status", _NEUTRAL_DOT)

        # Click the AUTO-SUBMIT action: it sends the Enter that completes the
        # single line already holding the drafted text.
        send_chip = actions_panel.get_action_chip_by_name("Send Now")
        expect(send_chip).to_be_enabled()
        send_chip.click()

        # One RECEIVED line carries BOTH prompts — proof the draft was inserted
        # but held until the auto-submit action sent the Enter.
        wait_for_xterm_substring(page, "RECEIVED:DRAFT-INSERT-PARTSEND-NOW-PART")
    finally:
        (registrations_dir / "fake-prompts.toml").unlink(missing_ok=True)
