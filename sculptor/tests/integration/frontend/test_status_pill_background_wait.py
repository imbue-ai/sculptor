"""Integration test for SCU-387: the status pill must not say "Thinking..." /
"Streaming..." / "Calling tools..." while the harness is sitting idle waiting
for a background task notification.

Repro shape: the agent emits its content + a result/success message and the
output processor stays alive until the in-flight background task delivers its
``task_notification``.  During that window the harness is genuinely idle —
``RequestSuccess`` has not been emitted yet, so ``taskStatus`` is still
``RUNNING`` and ``workingUserMessageId`` is still set.  The pill keeps showing
an active label, which is wrong.

The FakeClaude ``background_subagent`` command accepts ``pause_path`` to
expose this exact window: after step 4 (launched text + result/success) it
flushes those messages to stdout and blocks until the sentinel file at
``pause_path`` exists before emitting the task_notification. Tests use
``FakeClaudePause`` to get a unique sentinel path and call ``release()`` to
unblock — no wall-clock involved.
"""

import json

from playwright.sync_api import expect

from sculptor.testing.fake_claude_pause import FakeClaudePause
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story(
    "to verify the status pill does not claim activity while the harness waits for a background task notification"
)
def test_status_pill_shows_waiting_during_background_task(sculptor_instance_: SculptorInstance) -> None:
    """The pill must show a ``waiting`` label, not ``Thinking`` / ``Streaming``
    / ``Calling tools``, while the harness is idle waiting for a background
    task notification.

    Flow:
    1. Start a turn with ``background_subagent`` configured to pause after
       result/success via a sentinel file.
    2. Once the "launched" text is visible the harness has entered the wait
       window — assert the pill state.
    3. ``release()`` the sentinel; the agent emits the task_notification and
       the turn completes naturally. Assert the summary text and that the pill
       returns to idle.
    """
    page = sculptor_instance_.page
    pause = FakeClaudePause()

    bg_command = (
        "fake_claude:background_subagent `"
        + json.dumps(
            {
                "description": "Find Python files",
                "summary_text": "[SCU-387] background subagent done",
                "pause_path": str(pause.release_path),
            }
        )
        + "`"
    )

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=bg_command,
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # The "launched" text marks entry into the wait state — once it's visible,
    # FakeClaude has flushed step 4 (launched text + result/success) and is
    # now blocked on the sentinel file inside ``handle_background_subagent``.
    messages = chat_panel.get_messages()
    expect(messages.filter(has_text="Background subagent launched").first).to_be_visible()

    # Assert the pill is in the ``waiting`` lifecycle state — NOT
    # ``thinking`` / ``streaming`` / ``calling_tools``. The pill has its own
    # ~500ms debounce, but Playwright's default ``expect()`` timeout (30s) is
    # plenty for the transition to land.
    pill = chat_panel.get_status_pill()
    expect(pill).to_have_attribute("data-agent-state", "waiting_for_background")
    expect(chat_panel.get_status_pill_label()).to_contain_text("Waiting")

    # Release the agent. The task_notification + summary should now stream
    # through and the turn complete.
    pause.release()

    expect(messages.filter(has_text="[SCU-387] background subagent done").first).to_be_visible()
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()
