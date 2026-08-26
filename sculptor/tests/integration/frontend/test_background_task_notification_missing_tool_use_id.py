"""Regression test for SCU-1666: a background-task notification missing ``tool_use_id``.

When a background task is orphaned by a process exit (e.g. the machine restarts
while the task is running), the Claude CLI reports it as failed on resume with a
``system/task_notification`` that has no ``tool_use_id`` — the launching tool
call's id was lost with the dead process. The agent must process that
notification gracefully and stay alive, rather than crashing on a missing key.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# Drive FakeClaude to emit a failed task_notification with NO tool_use_id
# (``"tool_use_id": null`` omits the field), mirroring the orphaned-on-restart
# message the real CLI emits, then a final text marker. If the notification
# crashes the output-processing thread the marker never renders.
ORPHANED_NOTIFICATION_COMMAND = """\
fake_claude:multi_step `{
  "steps": [
    {"command": "emit_task_notification", "args": {
      "task_id": "a924753e20158e44b",
      "tool_use_id": null,
      "status": "failed",
      "summary": "Background agent was running when the previous Claude Code process exited and did not complete."
    }},
    {"command": "text", "args": {"text": "Agent survived the orphaned notification — ORPHAN-NOTIFY-DONE"}}
  ]
}`"""


@user_story("to have my agent survive an orphaned background-task notification after a restart")
def test_task_notification_without_tool_use_id_does_not_crash_agent(
    sculptor_instance_: SculptorInstance,
) -> None:
    """A task_notification missing tool_use_id must not kill the agent.

    Repro: FakeClaude emits a failed ``task_notification`` with no
    ``tool_use_id`` followed by a text marker. Before the fix,
    ``_handle_task_notification_message`` indexed ``data["tool_use_id"]``
    directly, so the missing key raised ``KeyError: 'tool_use_id'`` on the
    output-processing thread and crashed the whole agent (the marker never
    rendered and the turn ended in an error). With the fix the notification is
    handled, the marker renders, and follow-up turns still work.
    """
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt=ORPHANED_NOTIFICATION_COMMAND,
    )
    chat_panel = task_page.get_chat_panel()

    # The turn should finish (not hang), and the post-notification marker must
    # render — proof the agent kept processing after the malformed message.
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()
    expect(chat_panel.get_messages().filter(has_text="ORPHAN-NOTIFY-DONE").first).to_be_visible()

    # The missing key must not surface as a crash / error block.
    expect(chat_panel.get_error_block()).to_have_count(0)

    # The agent should still be usable — send a follow-up message.
    send_chat_message(chat_panel, 'fake_claude:text `{"text": "Recovery after orphaned notification"}`')
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()
    expect(chat_panel.get_messages().last).to_contain_text("Recovery after orphaned notification")
