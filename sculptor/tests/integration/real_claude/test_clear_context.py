"""Real Claude integration test: /clear starts a fresh session.

Verifies that the /clear pseudo-skill actually deletes the session-id state
file, so the next prompt runs in a new Claude session rather than resuming
the previous one.
"""

import pytest
from playwright.sync_api import expect

from sculptor.testing.elements.base import type_trigger_char
from sculptor.testing.sculptor_instance import SculptorInstance
from tests.integration.real_claude.helpers import assert_last_message_contains
from tests.integration.real_claude.helpers import assert_no_errors
from tests.integration.real_claude.helpers import create_workspace_and_send
from tests.integration.real_claude.helpers import real_claude
from tests.integration.real_claude.helpers import send_and_wait


@real_claude
@pytest.mark.timeout(300)
def test_clear_pseudo_skill_starts_fresh_session(sculptor_instance_: SculptorInstance) -> None:
    """/clear should delete the session-id file so the next prompt starts a new session.

    If the bug regressed, the session-id file would persist and the next
    prompt would resume the old conversation, causing Claude to still
    remember the secret code.
    """
    page = sculptor_instance_.page

    task_page = create_workspace_and_send(
        sculptor_instance_,
        "I am going to give you a secret code. Remember it. The code is: KRYPTON-55812. Reply with exactly: CODE-RECEIVED.",
    )
    chat_panel = task_page.get_chat_panel()
    assert_last_message_contains(chat_panel, "CODE-RECEIVED")

    chat_input = chat_panel.get_chat_input()
    type_trigger_char(chat_input, "/")
    chat_input.press_sequentially("clear")
    expect(chat_panel.get_mention_list()).to_be_visible(timeout=60_000)
    page.keyboard.press("Enter")
    chat_panel.get_send_button().click()

    expect(chat_panel.get_context_summary_messages()).to_be_visible(timeout=60_000)

    send_and_wait(
        chat_panel,
        "What secret code did I tell you earlier? If you do not know, reply with exactly: NO-CODE-REMEMBERED. Otherwise reply in the format: THE-CODE-IS: <code>",
    )
    assert_last_message_contains(chat_panel, "NO-CODE-REMEMBERED")
    assert_no_errors(chat_panel)
