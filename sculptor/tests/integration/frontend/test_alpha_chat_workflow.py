"""Integration tests for the Workflow pill and its master-detail popover.

The Workflow tool's tool_result returns immediately ("launched in
background") while the run continues as a background task streaming
system/task_progress deltas. The workflow renders as a subagent-style pill
describing the run, and its popover shows a Phases sidebar plus expandable
per-agent rows (Prompt / Activity / Outcome).

The FakeClaude ``workflow_run`` command emits the full lifecycle and accepts
``pause_path`` to block between the running tree and the completion deltas,
so the in-flight state can be asserted deterministically. Use
``FakeClaudePause`` for the sentinel and call ``release()`` to unblock.
"""

import json

from playwright.sync_api import expect

from sculptor.testing.elements.alpha_chat_view import scroll_alpha_chat_to_top
from sculptor.testing.fake_claude_pause import FakeClaudePause
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to watch a workflow's agents progress live from the Workflow pill")
def test_workflow_pill_shows_live_progress_then_final_tree(sculptor_instance_: SculptorInstance) -> None:
    """The Workflow pill describes the run and stays in the running state
    while in flight; the popover shows the phase sidebar with live agent
    states, and after completion an expanded agent row shows its outcome.
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

    # The pill renders subagent-style with a description of the run and stays
    # in the running state even though the tool_result has already arrived.
    workflow_pill = chat_panel.get_workflow_pills().first
    expect(workflow_pill).to_have_attribute("data-workflow-status", "running")
    expect(workflow_pill).to_contain_text("Workflow review-changes")
    expect(workflow_pill).to_contain_text("agents")

    # Open the popover: header with name + status, the Review phase in the
    # sidebar with its agent count, and the live agent rows.
    workflow_pill.click()
    popover = chat_panel.get_workflow_popover()
    expect(popover).to_be_visible()
    expect(popover).to_contain_text("review-changes")
    expect(popover).to_contain_text("Running…")
    phase_tab = chat_panel.get_workflow_phase_tabs().first
    expect(phase_tab).to_contain_text("Review")
    expect(phase_tab).to_contain_text("0/2")
    expect(popover).to_contain_text("review:bugs")
    expect(popover).to_contain_text("review:perf")

    # Expand the running agent: Prompt and Outcome sections appear, with the
    # latest tool activity accumulated from the progress deltas.
    agent_row = chat_panel.get_workflow_agent_rows().first
    agent_row.click()
    expect(popover).to_contain_text("Prompt")
    expect(popover).to_contain_text("Activity")
    expect(popover).to_contain_text("Grep: TODO in src/")
    expect(popover).to_contain_text("Still running…")

    # Close the popover before releasing — the completion turn scrolls the
    # chat, which auto-dismisses open popovers.
    workflow_pill.click()
    expect(popover).not_to_be_visible()

    # Release the workflow: the completion deltas, notification, and summary
    # turn stream through and the turn completes.
    pause.release()
    expect(messages.filter(has_text="[workflow-test] workflow done").first).to_be_visible()

    # The summary turn scrolls the chat to the newest message and the
    # virtualizer unmounts the earlier rows — scroll back up so the pill is
    # mounted again before asserting on it.
    scroll_alpha_chat_to_top(page)
    expect(workflow_pill).to_have_attribute("data-workflow-status", "completed")
    expect(workflow_pill).to_contain_text("2 agents")

    # Reopen the popover: the final tree persists; an expanded agent row now
    # shows its result preview as the outcome.
    workflow_pill.click()
    expect(popover).to_be_visible()
    expect(popover).to_contain_text("Completed")
    expect(chat_panel.get_workflow_phase_tabs().first).to_contain_text("2/2")
    chat_panel.get_workflow_agent_rows().first.click()
    expect(popover).to_contain_text("Found 2 bugs")
