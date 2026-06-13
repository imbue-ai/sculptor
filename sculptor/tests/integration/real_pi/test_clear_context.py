"""Real pi integration test: /clear starts a fresh conversation.

Plants a codeword on a real ``pi --mode rpc`` turn, runs the ``/clear``
pseudo-skill (which sends ``new_session`` between turns), then asks the agent to
recall the codeword. A correct refusal (``NO-CODE-REMEMBERED``) proves
``new_session`` genuinely cleared the session — the agent has no record of the
pre-clear turn. Mirrors ``real_claude/test_clear_context.py``.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from sculptor.interfaces.agents.agent import HarnessName
from sculptor.testing.elements.base import type_trigger_char
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from tests.integration.real_pi.helpers import RESPONSE_TIMEOUT_MS
from tests.integration.real_pi.helpers import prefixed
from tests.integration.real_pi.helpers import real_pi

_SENTINEL = "KRYPTON-55812"


@real_pi
@pytest.mark.timeout(600)
def test_real_pi_clear_resets_context(sculptor_instance_: SculptorInstance) -> None:
    """/clear must reset the real pi session so the next turn cannot recall the codeword.

    If the reset regressed (e.g. ``new_session`` not sent, or the persisted
    session id not advanced), pi would still hold the pre-clear turn and answer
    with the codeword instead of NO-CODE-REMEMBERED.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        workspace_name="Real Pi Clear",
        prompt=prefixed(f"Remember this codeword: {_SENTINEL}. Reply with exactly OK and nothing else."),
        model_name=None,
        harness=HarnessName.PI,
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=RESPONSE_TIMEOUT_MS)

    # Run the /clear pseudo-skill (sends new_session between turns). Mirrors the
    # real_claude clear flow: type the slash trigger, pick it from the mention
    # list, then send.
    chat_input = chat_panel.get_chat_input()
    type_trigger_char(chat_input, "/")
    chat_input.press_sequentially("clear")
    expect(chat_panel.get_mention_list()).to_be_visible(timeout=60_000)
    page.keyboard.press("Enter")
    chat_panel.get_send_button().click()
    expect(chat_panel.get_context_summary_messages()).to_be_visible(timeout=60_000)

    # After the reset, the agent must not recall the pre-clear codeword. Assert on
    # the last assistant reply (long timeout) rather than an exact message count —
    # the Context Cleared summary makes the post-clear row count ambiguous.
    send_chat_message(
        chat_panel=chat_panel,
        message=prefixed(
            "What codeword did I ask you to remember earlier? If you do not know, reply with exactly "
            "NO-CODE-REMEMBERED. Otherwise reply in the format THE-CODE-IS: <code>."
        ),
    )
    expect(chat_panel.get_assistant_messages().last).to_contain_text("NO-CODE-REMEMBERED", timeout=RESPONSE_TIMEOUT_MS)
    expect(chat_panel.get_error_block()).to_have_count(0)
