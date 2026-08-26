"""Integration test for SCU-1660: a task-notification turn colliding with a user prompt.

When a Monitor background task completes at (or very near) the instant a new
user prompt is dispatched, the Claude CLI delivers the pending
``<task-notification>`` as its own turn (init -> assistant -> result) *ahead*
of the user's message turn — all inside the single CLI process Sculptor spawned
for that prompt. The turn-completion loop must not treat the notification
turn's ``result`` as the end of the invocation; if it does, the CLI is torn
down while the user's real request has run at most one tool call, silently
abandoning it.

FakeClaude reproduces the collision deterministically via the
``notification_turn_then_response`` command, which scripts the exact
notification-turn-then-user-turn frame order that the timing race produces.
"""

from playwright.sync_api import expect

from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

NOTIFICATION_ACK_TEXT = "NOTIF-ACK stale Monitor task cleaned up"
USER_TURN_DONE_TEXT = "USER-TURN-COMPLETE merged and repushed"

NOTIFICATION_BEFORE_USER_TURN_COMMAND = f"""\
fake_claude:notification_turn_then_response `{{
  "task_id": "task-watchdog",
  "tool_use_id": "toolu-watchdog",
  "summary": "test-unit watcher finished",
  "ack_text": "{NOTIFICATION_ACK_TEXT}",
  "user_pre_text": "I'll fetch the latest state of that branch.",
  "user_tool_command": "git fetch origin",
  "user_post_text": "{USER_TURN_DONE_TEXT}"
}}`"""


@user_story("to verify a user prompt is not abandoned when a task-notification turn precedes it")
def test_user_turn_after_notification_turn_completes(sculptor_instance_: SculptorInstance) -> None:
    """The user's turn must run to completion even when a task-notification turn
    is delivered ahead of it within the same CLI process.

    Before the fix the output loop exits at the notification turn's ``result``,
    so the user turn's Bash tool call and its post-tool continuation never reach
    the chat — the request is abandoned after (at most) its first tool result.
    With the fix, the loop stays open until the user turn's own result, so the
    full response renders.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=NOTIFICATION_BEFORE_USER_TURN_COMMAND,
    )
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()

    messages = chat_panel.get_messages()

    # The notification turn's acknowledgement should be present (both turns ran).
    expect(messages.filter(has_text=NOTIFICATION_ACK_TEXT).first).to_be_visible()

    # The crux: the user turn's post-tool continuation must be visible. Its
    # absence is exactly the silent abandonment SCU-1660 describes.
    expect(messages.filter(has_text=USER_TURN_DONE_TEXT).first).to_be_visible()

    # The user turn's Bash tool call must also have rendered — the request got
    # past its first tool result rather than stalling on it. (Bash renders as a
    # dedicated bash block, not a generic tool pill.) When the turn is abandoned
    # no bash block renders at all.
    expect(chat_panel.get_bash_blocks()).to_have_count(1)
