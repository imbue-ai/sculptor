"""Regression test: the agent task list must survive a backend restart.

Bug origin (SCU-1245): the Python backend kept a host-side artifact cache
(`task_sync_dir`) under `gettempdir()` that the agent-tasks popover read
from. macOS's periodic jobs prune `$TMPDIR`, so a restart after a prune
surfaced an empty popover even though the per-emit PLAN-* snapshots were
intact.

The TypeScript backend removes that failure mode by construction: with the
single local environment (RW-SIMP-1) there is no remote-to-host artifact
sync and no reapable `$TMPDIR` cache. The agent's task list is written once
to the workspace's stable artifacts dir
(`<workspace>/artifacts/tasks/<agent>/PLAN-tasks.json`) and served straight
from there, and the `UpdatedArtifactAgentMessage` that points at it is in the
append-only log. So the popover repopulates from durable state on every
restart with nothing to back-fill. This test pins that end-to-end: create a
task list, restart, and assert it is still there.
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.plan_item import get_plan_checkmark
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

SECONDS_MS = 1000
_VISIBILITY_TIMEOUT_MS = 10 * SECONDS_MS
_BUILD_TIMEOUT_MS = 90 * SECONDS_MS


@user_story("to keep my agent's task list after Sculptor restarts")
def test_task_list_survives_restart_from_durable_state(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """Task list items must reappear after a restart, read from durable state.

    Steps:
    1. Start a task that creates tasks via TaskCreate.
    2. Verify the tasks appear in the StatusPill popover.
    3. Shut down Sculptor (exit context).
    4. Restart Sculptor against the same sculptor_folder and verify the tasks
       are still visible — proving they are served from the workspace's stable
       artifacts dir (and the persisted UpdatedArtifactAgentMessage), not from
       a transient cache.
    """
    with sculptor_instance_factory_.spawn_instance() as instance:
        task_page = start_task_and_wait_for_ready(
            instance.page,
            prompt="""\
fake_claude:multi_step `{
  "steps": [
    {"command": "task_create", "args": {"id": "1", "subject": "Investigate the bug", "status": "completed", "activeForm": "Investigating the bug"}},
    {"command": "task_create", "args": {"id": "2", "subject": "Write a failing test", "status": "in_progress", "activeForm": "Writing a failing test"}},
    {"command": "task_create", "args": {"id": "3", "subject": "Implement the fix", "status": "pending", "activeForm": "Implementing the fix"}}
  ]
}`""",
            wait_for_agent_to_finish=False,
        )

        chat_panel = task_page.get_chat_panel()
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

        status_pill = instance.page.get_by_test_id(ElementIDs.STATUS_PILL)
        expect(status_pill).to_be_visible()
        status_pill.click()
        rows = instance.page.get_by_test_id(ElementIDs.AGENT_TASKS_ROW)
        expect(rows).to_have_count(3)
        expect(rows.nth(0)).to_contain_text("Investigate the bug")
        expect(rows.nth(1)).to_contain_text("Write a failing test")
        expect(rows.nth(2)).to_contain_text("Implement the fix")

    # Sculptor is now down. The task list lives only in durable state (the
    # workspace's stable PLAN-tasks.json artifact plus the persisted
    # UpdatedArtifactAgentMessage); restarting must surface it again.
    with sculptor_instance_factory_.spawn_instance() as instance:
        workspace_tab = instance.page.get_by_test_id(ElementIDs.WORKSPACE_TAB).first
        expect(workspace_tab).to_be_visible(timeout=_VISIBILITY_TIMEOUT_MS)
        workspace_tab.click()

        agent_tab = instance.page.get_by_test_id(ElementIDs.AGENT_TAB).first
        expect(agent_tab).to_be_visible(timeout=_BUILD_TIMEOUT_MS)
        agent_tab.click()

        status_pill = instance.page.get_by_test_id(ElementIDs.STATUS_PILL)
        expect(status_pill).to_be_visible(timeout=_BUILD_TIMEOUT_MS)
        status_pill.click()
        rows = instance.page.get_by_test_id(ElementIDs.AGENT_TASKS_ROW)
        expect(rows).to_have_count(3, timeout=_BUILD_TIMEOUT_MS)

        expect(rows.nth(0)).to_contain_text("Investigate the bug")
        expect(rows.nth(1)).to_contain_text("Write a failing test")
        expect(rows.nth(2)).to_contain_text("Implement the fix")

        expect(get_plan_checkmark(plan_item=rows.nth(0))).to_have_count(1)
        expect(get_plan_checkmark(plan_item=rows.nth(1))).to_have_count(0)
        expect(get_plan_checkmark(plan_item=rows.nth(2))).to_have_count(0)
