"""Real Claude integration tests: basic message flow.

Verifies that the stdin JSON protocol (--input-format stream-json) delivers
prompts and receives responses correctly, including across session resumes.
"""

import pytest

from sculptor.testing.sculptor_instance import SculptorInstance
from tests.integration.real_claude.helpers import assert_any_message_contains
from tests.integration.real_claude.helpers import assert_last_message_contains
from tests.integration.real_claude.helpers import assert_no_errors
from tests.integration.real_claude.helpers import create_workspace_and_send
from tests.integration.real_claude.helpers import real_claude
from tests.integration.real_claude.helpers import send_and_wait


@real_claude
@pytest.mark.timeout(300)
def test_single_message_response(sculptor_instance_: SculptorInstance) -> None:
    """Verify the stdin JSON protocol delivers a prompt and receives a response."""
    task_page = create_workspace_and_send(
        sculptor_instance_,
        "Reply with exactly the text PONG-91827. Do not add any other text, formatting, or explanation.",
    )
    chat_panel = task_page.get_chat_panel()
    assert_last_message_contains(chat_panel, "PONG-91827")
    assert_no_errors(chat_panel)


@real_claude
@pytest.mark.timeout(300)
def test_multiple_sequential_messages(sculptor_instance_: SculptorInstance) -> None:
    """Verify stdin protocol works for multiple messages within one session."""
    task_page = create_workspace_and_send(
        sculptor_instance_,
        "Reply with exactly: FIRST-82734. Nothing else.",
    )
    chat_panel = task_page.get_chat_panel()
    assert_last_message_contains(chat_panel, "FIRST-82734")

    send_and_wait(chat_panel, "Reply with exactly: SECOND-49105. Nothing else.")
    assert_last_message_contains(chat_panel, "SECOND-49105")

    send_and_wait(chat_panel, "Reply with exactly: THIRD-63928. Nothing else.")
    assert_last_message_contains(chat_panel, "THIRD-63928")

    # Earlier messages should still be visible
    assert_any_message_contains(chat_panel, "FIRST-82734")
    assert_any_message_contains(chat_panel, "SECOND-49105")


@real_claude
@pytest.mark.timeout(300)
def test_conversation_context_preserved_across_messages(sculptor_instance_: SculptorInstance) -> None:
    """Verify --resume carries conversation history between messages."""
    task_page = create_workspace_and_send(
        sculptor_instance_,
        "I am going to give you a secret code. Remember it. The code is: KRYPTON-55812. Reply with exactly: CODE-RECEIVED.",
    )
    chat_panel = task_page.get_chat_panel()
    assert_last_message_contains(chat_panel, "CODE-RECEIVED")

    send_and_wait(chat_panel, "What is the secret code I told you? Reply in the format: THE-CODE-IS: <code>")
    assert_last_message_contains(chat_panel, "KRYPTON-55812")


@real_claude
@pytest.mark.timeout(600)
def test_message_after_context_compaction(sculptor_instance_: SculptorInstance) -> None:
    """Verify the compact flow works with stdin JSON protocol.

    This test triggers auto-compaction by having the agent read many files to
    fill context past the CLAUDE_AUTOCOMPACT_PCT_OVERRIDE threshold.

    NOTE: This test is deferred — triggering compaction reliably requires
    CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=30 to be injected into the agent process
    environment, which needs test harness changes.
    """
    pytest.skip(
        "Deferred: triggering compaction reliably requires CLAUDE_AUTOCOMPACT_PCT_OVERRIDE to be injected into the agent environment, which needs test harness changes."
    )
