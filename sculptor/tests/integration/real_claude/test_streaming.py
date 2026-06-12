"""Real Claude integration tests: streaming.

Verifies that streaming works end-to-end with the stdin protocol — text
appears progressively and no content is dropped.
"""

import pytest
from playwright.sync_api import expect

from sculptor.testing.sculptor_instance import SculptorInstance
from tests.integration.real_claude.helpers import RESPONSE_TIMEOUT_MS
from tests.integration.real_claude.helpers import assert_last_message_contains
from tests.integration.real_claude.helpers import assert_no_errors
from tests.integration.real_claude.helpers import create_workspace_and_send
from tests.integration.real_claude.helpers import real_claude
from tests.integration.real_claude.helpers import wait_for_streaming_text


@real_claude
@pytest.mark.timeout(300)
def test_long_streaming_response(sculptor_instance_: SculptorInstance) -> None:
    """Verify streaming works (text appears progressively, not batched)."""
    task_page = create_workspace_and_send(
        sculptor_instance_,
        (
            "Print the numbers 1 through 100, each on its own line, in the format 'NUM-001', 'NUM-002', etc. Use zero-padded three-digit numbers. Do not add any other text."
        ),
        wait_for_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Streaming check: NUM-001 should appear well before the agent finishes
    wait_for_streaming_text(chat_panel, "NUM-001", timeout_ms=30_000)

    # Wait for completion
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=RESPONSE_TIMEOUT_MS)

    # Spot-check: beginning, middle, and end
    assert_last_message_contains(chat_panel, "NUM-001")
    assert_last_message_contains(chat_panel, "NUM-050")
    assert_last_message_contains(chat_panel, "NUM-100")
    assert_no_errors(chat_panel)


@real_claude
@pytest.mark.timeout(300)
def test_streaming_does_not_drop_content(sculptor_instance_: SculptorInstance) -> None:
    """Verify no content is dropped during streaming."""
    task_page = create_workspace_and_send(
        sculptor_instance_,
        (
            "Output exactly 20 lines. Line K should read 'CHECKPOINT-K-VERIFIED' where K goes from 01 to 20. Zero-pad K to two digits. No other text."
        ),
    )
    chat_panel = task_page.get_chat_panel()

    # Verify all 20 checkpoints are present
    for i in range(1, 21):
        assert_last_message_contains(chat_panel, f"CHECKPOINT-{i:02d}-VERIFIED")
