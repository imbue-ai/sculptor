"""Real Claude integration tests: ScheduleWakeup tool.

Verifies that when Claude calls ScheduleWakeup, Sculptor keeps the CLI process
alive until the wakeup fires and the second turn completes — rather than killing
the process after the first result message.

The ScheduleWakeup protocol on stdout looks like:

    Turn 1:  init → assistant (tool_use ScheduleWakeup) → user (tool_result) → result
    ~delay~
    Turn 2:  init → assistant → result

Sculptor must keep the process alive across the delay between the two turns.
"""

import pytest
from playwright.sync_api import expect

from sculptor.testing.sculptor_instance import SculptorInstance
from tests.integration.real_claude.helpers import _get_assistant_messages
from tests.integration.real_claude.helpers import assert_no_errors
from tests.integration.real_claude.helpers import create_workspace_and_send
from tests.integration.real_claude.helpers import real_claude

# ScheduleWakeup clamps delaySeconds to [60, 3600]. We use the minimum to keep
# the test fast, but it still needs ~2 minutes total (60s delay + turn time).
_WAKEUP_DELAY_SECONDS = 60


@real_claude
@pytest.mark.timeout(300)
def test_schedule_wakeup_second_turn_delivered(sculptor_instance_: SculptorInstance) -> None:
    """ScheduleWakeup fires and the wakeup turn response reaches the UI.

    The agent calls ScheduleWakeup, which ends the first turn. After the delay,
    Claude Code fires a second turn. Sculptor must keep the process alive across
    the gap and deliver the second turn's response to the UI.

    With the bug: the process is killed after the first result message, so the
    second turn never fires and the wakeup sentinel never appears.
    """
    task_page = create_workspace_and_send(
        sculptor_instance_,
        f"Call the ScheduleWakeup tool with delaySeconds={_WAKEUP_DELAY_SECONDS}, reason='integration test', and prompt='Say exactly: WAKEUP-DELIVERED-93047'. Do nothing else — just call ScheduleWakeup and end your turn.",
        wait_for_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # The wakeup turn should deliver the sentinel. The total wait is:
    # ~10s for first turn + 60s wakeup delay + ~10s for second turn = ~80s.
    # Empirically saw a run land at 129s which is just over the 120s default,
    # so give 180s of headroom for model variance.
    # Check assistant messages only to avoid matching the user's instruction text.
    assistant_msgs = _get_assistant_messages(chat_panel)
    expect(assistant_msgs.filter(has_text="WAKEUP-DELIVERED-93047").first).to_be_visible(
        timeout=180_000,
    )
    assert_no_errors(chat_panel)
