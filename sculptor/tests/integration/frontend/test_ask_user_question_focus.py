"""Regression test: AskUserQuestion must not steal focus from the terminal.

When the agent invokes ``AskUserQuestion`` while the user is typing in the
terminal, the answering panel should not steal focus.  Otherwise keypresses
intended for the terminal are routed to the panel's keyboard handler and
dropped.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.ask_user_question import get_ask_user_question_panel
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.terminal import get_terminal_textarea
from sculptor.testing.elements.terminal import open_terminal_and_wait
from sculptor.testing.elements.terminal import type_with_global_keyboard
from sculptor.testing.elements.terminal import wait_for_xterm_substring
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

_QUESTION_PROMPT = """\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "What language do you prefer?",
      "header": "Language",
      "options": [
        {"label": "Python", "description": "A versatile language"},
        {"label": "Rust", "description": "For systems programming"}
      ],
      "multiSelect": false
    }
  ]
}`"""


@user_story("to keep typing in the terminal when the agent opens an AskUserQuestion panel")
def test_ask_user_question_does_not_steal_focus_from_terminal(
    sculptor_instance_: SculptorInstance,
) -> None:
    """The AskUserQuestion panel must not steal focus from the terminal on mount.

    Steps:
    1. Create a workspace and open the terminal panel
    2. Focus the terminal's hidden xterm textarea (as if the user clicked into it)
    3. Send a chat message that triggers an AskUserQuestion tool call
    4. Wait for the AUQ panel to appear
    5. Prove the terminal still owns keyboard input: type a probe and confirm it
       lands in the xterm buffer (not the AUQ panel)
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")
    open_terminal_and_wait(page)

    terminal_textarea = get_terminal_textarea(page)

    # Send a chat message that will trigger the AUQ.  ``send_chat_message``
    # focuses the chat input, so we must move focus back to the terminal AFTER
    # sending — that's the real-world scenario: user kicks off the agent, then
    # clicks into the terminal to do something while the agent runs.
    send_chat_message(task_page.get_chat_panel(), _QUESTION_PROMPT)
    terminal_textarea.focus()

    # Sanity check: terminal currently has focus right before the AUQ mounts.
    expect(terminal_textarea).to_be_focused()

    # Wait for the AUQ panel to appear. Because expect() polls (well past the
    # AUQ's mount-time focus effect), the panel's focus-steal — if present — has
    # already fired by the time this returns.
    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel).to_be_visible()

    # The terminal textarea should still be the active element after the AUQ
    # panel mounts — the panel must not steal focus.
    expect(terminal_textarea).to_be_focused()

    # Prove the user-facing guarantee, not just the focus snapshot: type a probe
    # with the GLOBAL keyboard (routes to document.activeElement) and confirm it
    # reaches the shell. If the AUQ stole focus, the keystrokes go to its
    # keyboard handler instead and the marker never appears in the xterm buffer,
    # so wait_for_xterm_substring times out. The leading throwaway chars absorb
    # any keystrokes xterm may drop right as input begins.
    probe_marker = "AUQ_FOCUS_PROBE_OK"
    type_with_global_keyboard(page, "zzz " + probe_marker)
    wait_for_xterm_substring(page, probe_marker)
