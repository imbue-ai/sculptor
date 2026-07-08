"""Integration tests for background subagent (Agent tool with run_in_background) rendering.

Verifies that background subagent calls are rendered as an AlphaSubagentPill,
not as a generic tool pill; that a task_notification arriving mid-turn does
not split the surrounding tool batches into separate messages; and that an
Agent call the harness converts to a background task (no run_in_background in
its input — SCU-1792) gets live background status instead of the agent-facing
launch-ack.
"""

import json

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.fake_claude_pause import FakeClaudePause
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

BG_SUBAGENT_RESULT = "Found 10 Python files in the repository."
BG_SUMMARY_TEXT = "The background subagent found 10 Python files."
BG_PROMPT = "List all Python files"

BG_SUBAGENT_COMMAND = f"""\
fake_claude:background_subagent `{{
  "description": "Find Python files",
  "prompt": "{BG_PROMPT}",
  "subagent_result": "{BG_SUBAGENT_RESULT}",
  "summary_text": "{BG_SUMMARY_TEXT}"
}}`"""


@user_story("to verify that background subagent does not render as a generic tool pill")
def test_background_subagent_does_not_render_as_generic_tool_pill(sculptor_instance_: SculptorInstance) -> None:
    """Background Agent tool should not render as a generic alpha tool pill.

    Regression check: if the subagent tree fails to recognise the Agent tool,
    alpha would render it as a generic ALPHA_CHAT_TOOL_PILL with the
    "Async agent launched" tool-result text. The correct rendering is a
    subagent pill (or no inline tool pill at all when alpha collapses it).
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=BG_SUBAGENT_COMMAND,
    )
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()

    # The summary text from the post-notification response should be visible.
    messages = chat_panel.get_messages()
    expect(messages.filter(has_text=BG_SUMMARY_TEXT).first).to_be_visible()

    # The Agent tool must NOT render as a generic tool pill with the
    # "Async agent launched" tool-result text — that would be the regression.
    generic_agent_tool_pills = chat_panel.get_tool_pills().filter(has_text="Async agent launched")
    expect(generic_agent_tool_pills).to_have_count(0)


MID_TURN_NOTIFICATION_COMMAND = """\
fake_claude:multi_step `{
  "steps": [
    {"command": "parallel_tools", "args": {"tools": [
      {"tool_name": "Grep", "tool_input": {"pattern": "alpha"}},
      {"tool_name": "Grep", "tool_input": {"pattern": "beta"}},
      {"tool_name": "Grep", "tool_input": {"pattern": "gamma"}}
    ]}},
    {"command": "emit_task_notification", "args": {
      "task_id": "task-midturn",
      "tool_use_id": "toolu-midturn",
      "summary": "Background task done"
    }},
    {"command": "parallel_tools", "args": {"tools": [
      {"tool_name": "Grep", "tool_input": {"pattern": "delta"}},
      {"tool_name": "Grep", "tool_input": {"pattern": "epsilon"}},
      {"tool_name": "Grep", "tool_input": {"pattern": "zeta"}}
    ]}},
    {"command": "text", "args": {"text": "All 6 greps complete — MIDTURN-NOTIFY-DONE"}}
  ]
}`"""


@user_story("to verify that a background task notification arriving mid-turn does not split tool calls")
def test_mid_turn_notification_does_not_split_assistant_messages(sculptor_instance_: SculptorInstance) -> None:
    """Mid-turn task_notification must not split consecutive assistant content into separate messages.

    Repro: tool batch (3 Greps) → task_notification → tool batch (3 Greps) → text.
    All six Greps are part of the same turn with no RequestSuccess between them,
    so they should merge into a single assistant ChatMessage (and therefore a
    single rendered assistant message bubble). The notification must not act as
    a message boundary.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=MID_TURN_NOTIFICATION_COMMAND,
    )
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()

    # Wait for the final text so we know all messages have arrived.
    messages = chat_panel.get_messages()
    expect(messages.filter(has_text="MIDTURN-NOTIFY-DONE").first).to_be_visible()

    # Both batches of Greps should be visible. Before the fix, the notification
    # flushed the in-progress message; a new in-progress was then created with
    # the SAME first_response_message_id as the flushed one, producing two
    # ChatMessages with identical ids that the frontend's
    # mergeAndDeduplicateMessages then collapsed — silently losing the pre-
    # notification batch. The UI would show only ONE pill row.
    #
    # With the fix, the content accumulates in a single ChatMessage and the
    # two batches render as TWO pill rows (separated by the text prefix that
    # FakeClaude emits before each tool batch).
    pill_rows = chat_panel.get_tool_pill_rows()
    expect(pill_rows).to_have_count(2)
    expect(pill_rows.first.get_by_test_id(ElementIDs.ALPHA_CHAT_TOOL_PILL)).to_have_count(3)
    expect(pill_rows.last.get_by_test_id(ElementIDs.ALPHA_CHAT_TOOL_PILL)).to_have_count(3)


CONVERTED_SUMMARY_TEXT = "[SCU-1792] converted subagent finished"
CONVERTED_NOTIFICATION_SUMMARY = "Converted agent findings: all good."


@user_story("to verify that a harness-converted background agent shows live status instead of the launch-ack")
def test_converted_background_agent_shows_live_status_and_result(sculptor_instance_: SculptorInstance) -> None:
    """An Agent call converted to a background task (no run_in_background in
    its input) must render as a live background subagent pill: while the task
    runs the popover says so in user-facing terms, and the agent-facing
    launch-ack ("Async agent launched... agentId: ...") never surfaces.

    The only signal that the call went to the background is the
    background_task_id the backend stamps on the launch-ack ToolResultBlock
    (from the preceding task_started). Without the stamp, the pill freezes at
    ~0.0s and the popover shows the launch-ack as the agent's Response.
    """
    page = sculptor_instance_.page
    pause = FakeClaudePause()

    converted_command = (
        "fake_claude:background_subagent `"
        + json.dumps(
            {
                "description": "Investigate the repo",
                "prompt": "Investigate the repository layout",
                "converted": True,
                "summary_text": CONVERTED_SUMMARY_TEXT,
                "notification_summary": CONVERTED_NOTIFICATION_SUMMARY,
                "pause_path": str(pause.release_path),
            }
        )
        + "`"
    )

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=converted_command,
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # The "launched" text marks entry into the wait window: FakeClaude flushed
    # the turn (tool_use → task_started → launch-ack → result/success) and is
    # blocked on the sentinel before emitting the task_notification.
    messages = chat_panel.get_messages()
    expect(messages.filter(has_text="Background subagent launched").first).to_be_visible()

    # The converted call must render as a subagent pill, not a generic tool
    # pill showing the launch-ack.
    pill = chat_panel.get_subagent_pills()
    expect(pill).to_have_count(1)
    expect(chat_panel.get_tool_pills().filter(has_text="Async agent launched")).to_have_count(0)

    # Open the popover: while the task is pending it must show the user-facing
    # running status, and never the agent-facing launch-ack.
    pill.click()
    status = page.get_by_test_id(ElementIDs.ALPHA_CHAT_SUBAGENT_POPOVER_STATUS)
    expect(status).to_be_visible()
    expect(status).to_contain_text("Running in the background")
    note = page.get_by_test_id(ElementIDs.ALPHA_CHAT_SUBAGENT_POPOVER_NOTE)
    expect(note).to_be_visible()
    expect(note).to_contain_text("aren't shown")
    expect(status).not_to_contain_text("Async agent launched")
    # Close the popover so it doesn't interfere with the post-release steps.
    page.keyboard.press("Escape")

    # Release: the task_notification and the follow-up summary turn arrive.
    pause.release()
    expect(messages.filter(has_text=CONVERTED_SUMMARY_TEXT).first).to_be_visible()
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()

    # The completion child synthesized from the notification becomes the
    # pill's Response — reopen the popover and check the summary shows and
    # the running status is gone.
    pill.click()
    response = page.get_by_test_id(ElementIDs.ALPHA_CHAT_SUBAGENT_POPOVER_RESPONSE)
    expect(response).to_be_visible()
    expect(response).to_contain_text(CONVERTED_NOTIFICATION_SUMMARY)
    expect(page.get_by_test_id(ElementIDs.ALPHA_CHAT_SUBAGENT_POPOVER_STATUS)).not_to_be_visible()

    # The launch-ack must not appear anywhere in the chat.
    expect(chat_panel.get_messages().filter(has_text="Async agent launched")).to_have_count(0)
