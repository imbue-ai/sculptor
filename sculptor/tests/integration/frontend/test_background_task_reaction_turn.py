"""Integration test for a test-timed background completion that fires a
spontaneous reaction turn.

The ``start_background_task`` FakeClaude command arms a background task and ends
the arming turn (its ``result`` is emitted, the process lingers). When the test
creates the trigger sentinel, FakeClaude emits ``task_updated`` +
``task_notification`` and then a full ``init -> reaction -> result`` cycle —
without any user frame prompting it, matching the real CLI's spontaneous
reaction turn on background-task completion.

Unlike ``background_subagent`` (whose notification + reaction are baked into the
same cycle as the launch), here the reaction is a genuinely separate cycle
emitted while the process idles between cycles, so completion timing is fully
test-controlled via ``FakeClaudeTrigger``.
"""

import json

from playwright.sync_api import expect

from sculptor.testing.fake_claude_pause import FakeClaudeTrigger
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to verify a background task completing while idle fires a spontaneous reaction turn")
def test_idle_background_completion_fires_reaction_turn(sculptor_instance_: SculptorInstance) -> None:
    """Flow:
    1. Start a turn with ``start_background_task``; the arming turn ends and the
       harness lingers waiting for the background completion.
    2. Once the "launched" text is visible, assert the pill shows the
       ``waiting_for_background`` lifecycle state.
    3. ``fire()`` the trigger; FakeClaude emits the completion and its reaction
       cycle. Assert the reaction summary appears and the pill returns to idle.
    """
    page = sculptor_instance_.page
    trigger = FakeClaudeTrigger()

    arm_command = (
        "fake_claude:start_background_task `"
        + json.dumps(
            {
                "description": "Find Python files",
                "reaction_text": "[SCU-1680] reaction turn complete",
                "notification_summary": "background task done",
                "trigger_path": str(trigger.trigger_path),
            }
        )
        + "`"
    )

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=arm_command,
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # The "launched" text marks the end of the arming turn: FakeClaude has
    # emitted task_started + result and is now lingering on the trigger sentinel.
    messages = chat_panel.get_messages()
    expect(messages.filter(has_text="Background task launched").first).to_be_visible()

    # The harness is idle with a pending background task — the pill must show the
    # waiting state, not an active label.
    pill = chat_panel.get_status_pill()
    expect(pill).to_have_attribute("data-agent-state", "waiting_for_background")
    expect(chat_panel.get_status_pill_label()).to_contain_text("Waiting")

    # Fire the completion. The spontaneous task_updated + task_notification +
    # reaction cycle should stream through and the turn complete.
    trigger.fire()

    expect(messages.filter(has_text="[SCU-1680] reaction turn complete").first).to_be_visible()
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()
