"""Integration tests for the Workflow tool pill and its progress popover.

The Workflow tool's tool_result returns immediately ("launched in
background") while the run continues as a background task streaming
system/task_progress events. The pill must stay in the executing state until
the task_notification arrives, and the popover must render the live
workflow_progress tree (phases and per-agent states).

The FakeClaude ``workflow_run`` command emits the full lifecycle and accepts
``pause_path`` to block between the running tree and the final tree, so the
in-flight state can be asserted deterministically. Use ``FakeClaudePause``
for the sentinel and call ``release()`` to unblock.
"""

import json

from playwright.sync_api import expect

from sculptor.testing.elements.alpha_chat_view import scroll_alpha_chat_to_top
from sculptor.testing.fake_claude_pause import FakeClaudePause
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to watch a workflow's agents progress live from the Workflow tool pill")
def test_workflow_pill_shows_live_progress_then_final_tree(sculptor_instance_: SculptorInstance) -> None:
    """The Workflow pill pulses while the run is in flight, its popover shows
    the running phase/agent tree, and after completion the pill settles to
    completed with the final tree (result previews) in the popover.
    """
    page = sculptor_instance_.page
    pause = FakeClaudePause()

    workflow_command = (
        "fake_claude:workflow_run `"
        + json.dumps(
            {
                "workflow_name": "review-changes",
                "summary_text": "[workflow-test] workflow done",
                "pause_path": str(pause.release_path),
            }
        )
        + "`"
    )

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=workflow_command,
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # The "launched" text marks the wait window: FakeClaude has flushed the
    # running tree + result/success and is blocked on the sentinel.
    messages = chat_panel.get_messages()
    expect(messages.filter(has_text="Workflow launched.").first).to_be_visible()

    # The pill stays in the executing state even though the tool_result has
    # already arrived — the workflow task is still running.
    workflow_pill = chat_panel.get_tool_pills().filter(has_text="Workflow").first
    expect(workflow_pill).to_have_attribute("data-tool-state", "initializing")

    # Open the popover and assert the live tree: workflow name + status,
    # phase section, one agent in progress (with its latest tool activity)
    # and one queued.
    workflow_pill.click()
    popover = chat_panel.get_tool_pill_popover()
    expect(popover).to_be_visible()
    expect(popover).to_contain_text("review-changes")
    expect(popover).to_contain_text("Running…")
    expect(popover).to_contain_text("Review")
    expect(popover).to_contain_text("review:bugs")
    expect(popover).to_contain_text("review:perf")
    expect(popover).to_contain_text("Grep: TODO in src/")

    # Close the popover before releasing — the completion turn scrolls the
    # chat, which auto-dismisses open popovers.
    workflow_pill.click()
    expect(popover).not_to_be_visible()

    # Release the workflow: the final tree, notification, and summary turn
    # stream through and the turn completes.
    pause.release()
    expect(messages.filter(has_text="[workflow-test] workflow done").first).to_be_visible()

    # The summary turn scrolls the chat to the newest message and the
    # virtualizer unmounts the earlier tool row — scroll back up so the pill
    # is mounted again before asserting on it.
    scroll_alpha_chat_to_top(page)
    expect(workflow_pill).to_have_attribute("data-tool-state", "completed")

    # Reopen the popover: the final tree persists with per-agent results.
    workflow_pill.click()
    expect(popover).to_be_visible()
    expect(popover).to_contain_text("Completed")
    expect(popover).to_contain_text("Found 2 bugs")
    expect(popover).to_contain_text("No perf issues")
