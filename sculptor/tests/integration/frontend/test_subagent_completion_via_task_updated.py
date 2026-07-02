"""UI-level coverage for SCU-1669: a subagent (Agent tool, ``task_type``
``local_agent``) that reports completion via ``task_updated`` — with its real
``task_notification`` + synthesis turn arriving only after a pause — is rendered
correctly and keeps the turn alive (pill in ``waiting_for_background``) until the
synthesis is delivered.

The main agent launches two background subagents and ends its turn while both are
pending. Subagent A completes normally (``task_notification`` + synthesis turn).
Subagent B instead reports ``task_updated{completed}`` with NO ``task_notification``
— which the CLI does when a task finishes while it is busy emitting another turn —
and only after a pause delivers its real notification + synthesis turn.

NOTE: the *deterministic* regression proof for SCU-1669 lives in
``output_processor_test.py::TestSubagentCompletionViaTaskUpdated`` — it drives the
production ``_process_output`` loop verbatim with the exact protocol frames. The
underlying race (a subagent cleared at an intervening turn's result before its
synthesis is read) depends on the real CLI's streaming timing, which FakeClaude's
synchronous flush does not reproduce; this test therefore exercises the UI path
rather than reproducing the race. It guards against gross breakage of subagent
completion rendering and the ``waiting_for_background`` turn state.
"""

from playwright.sync_api import expect

from sculptor.testing.fake_claude_pause import FakeClaudePause
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

SUBAGENT_A_SYNTHESIS = "SUBAGENT-A-SYNTHESIS-1669"
SUBAGENT_B_SYNTHESIS = "SUBAGENT-B-SYNTHESIS-1669"


def _subagent_task_updated_command(release_path: str) -> str:
    """Script the SCU-1669 repro, pausing before subagent B's synthesis turn.

    Steps: main turn launches two ``local_agent`` subagents; subagent A completes
    with a notification + synthesis; subagent B reports a terminal ``task_updated``
    (no notification); ``emit_result`` closes subagent A's synthesis turn (the
    boundary at which subagent B was wrongly cleared); the agent then parks on the
    sentinel; on release, subagent B's real notification + synthesis is delivered.
    """
    return f"""\
fake_claude:multi_step `{{
  "steps": [
    {{"command": "text", "args": {{"text": "Launching two exploration subagents."}}}},
    {{"command": "background_task_started", "args": {{
      "task_id": "sub-a", "tool_use_id": "toolu-sub-a",
      "description": "Explore frontend", "task_type": "local_agent"
    }}}},
    {{"command": "background_task_started", "args": {{
      "task_id": "sub-b", "tool_use_id": "toolu-sub-b",
      "description": "Explore backend", "task_type": "local_agent"
    }}}},
    {{"command": "background_task_notification", "args": {{
      "task_id": "sub-a", "tool_use_id": "toolu-sub-a",
      "response_text": "{SUBAGENT_A_SYNTHESIS}", "summary": "Frontend exploration done"
    }}}},
    {{"command": "emit_task_updated", "args": {{"task_id": "sub-b", "status": "completed"}}}},
    {{"command": "emit_result", "args": {{}}}},
    {{"command": "wait_for_file", "args": {{"path": "{release_path}"}}}},
    {{"command": "background_task_notification", "args": {{
      "task_id": "sub-b", "tool_use_id": "toolu-sub-b",
      "response_text": "{SUBAGENT_B_SYNTHESIS}", "summary": "Backend exploration done"
    }}}}
  ]
}}`"""


@user_story(
    "to verify a subagent completing via task_updated (no task_notification) does not end the turn prematurely"
)
def test_subagent_task_updated_does_not_end_turn_before_notification(
    sculptor_instance_: SculptorInstance,
) -> None:
    """A ``local_agent`` subagent whose completion arrives first as
    ``task_updated`` keeps the turn alive (pill ``waiting_for_background``) for
    its follow-up ``task_notification`` + synthesis turn, and both subagents'
    syntheses render.
    """
    page = sculptor_instance_.page
    pause = FakeClaudePause()

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=_subagent_task_updated_command(str(pause.release_path)),
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    messages = chat_panel.get_messages()
    # Subagent A completed normally — its synthesis confirms we've reached the
    # paused window (FakeClaude is now parked on the sentinel).
    expect(messages.filter(has_text=SUBAGENT_A_SYNTHESIS).first).to_be_visible()

    # The turn must still be open, waiting on subagent B. Before the fix the turn
    # had already ended here (subagent B cleared), so the pill would be idle.
    pill = chat_panel.get_status_pill()
    expect(pill).to_have_attribute("data-agent-state", "waiting_for_background")

    # Release the pause: FakeClaude delivers subagent B's notification + synthesis.
    pause.release()

    # Subagent B's synthesis must now be delivered. Before the fix the turn had
    # ended and the paused CLI was torn down, so this never arrived.
    expect(messages.filter(has_text=SUBAGENT_B_SYNTHESIS).first).to_be_visible()
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()
