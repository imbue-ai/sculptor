"""Regression test: task list should persist across application restarts.

Bug: When Sculptor restarts, the agent-tasks UI is emptied because
UpdatedArtifactAgentMessage is ephemeral and not re-emitted on reconnect.
The frontend only fetches artifacts when notified via WebSocket, and no
notification is sent for existing artifacts after restart.

Post-migration: the source-of-truth for tasks is now Claude Code's
per-task JSON files at $HOME/.claude/tasks/{session_id}/, and the PLAN
artifact on disk is a TaskListArtifact (v2) that survives restart via
the same task_service startup re-emission path.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.agent_tab import PlaywrightAgentTabBarElement
from sculptor.testing.elements.agent_tasks_popover import PlaywrightAgentTasksPopoverElement
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.plan_item import get_plan_checkmark
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

SECONDS_MS = 1000
_BUILD_TIMEOUT_MS = 90 * SECONDS_MS


@user_story("to see my agent's task list after restarting Sculptor")
def test_task_list_persists_after_restart(sculptor_instance_factory_: SculptorInstanceFactory) -> None:
    """Task list items should be visible after restarting Sculptor.

    Steps:
    1. Start a task that creates tasks via TaskCreate
    2. Verify the tasks appear in the StatusPill popover
    3. Shut down Sculptor (exit context)
    4. Restart Sculptor and navigate to the workspace
    5. Verify the tasks are still visible in the popover
    """
    # Phase 1: Create tasks, verify they appear, then shut down.
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

        # Open the StatusPill popover and verify task rows are visible.
        tasks_popover = PlaywrightAgentTasksPopoverElement(instance.page)
        tasks_popover.open()
        rows = tasks_popover.get_rows()
        expect(rows).to_have_count(3)
        expect(rows.nth(0)).to_contain_text("Investigate the bug")
        expect(rows.nth(1)).to_contain_text("Write a failing test")
        expect(rows.nth(2)).to_contain_text("Implement the fix")

    # Exiting the context shuts down Sculptor.

    # Phase 2: Restart and verify tasks are still present.
    with sculptor_instance_factory_.spawn_instance() as instance:
        # Navigate to the workspace (click on the persisted workspace tab).
        project_layout = PlaywrightProjectLayoutPage(instance.page)
        workspace_tab = project_layout.get_workspace_tabs().first
        expect(workspace_tab).to_be_visible()
        workspace_tab.click()

        # Wait for the agent tab to appear and click it to get to the task page.
        agent_tab_bar = PlaywrightAgentTabBarElement(instance.page)
        agent_tab = agent_tab_bar.get_agent_tabs().first
        expect(agent_tab).to_be_visible(timeout=_BUILD_TIMEOUT_MS)
        agent_tab.click()

        # The pill should reappear because there's a fresh (non-stale) task
        # artifact carried over from before the restart. Click it to open
        # the popover and verify items survived.
        tasks_popover = PlaywrightAgentTasksPopoverElement(instance.page)
        tasks_popover.open(timeout=_BUILD_TIMEOUT_MS)
        rows = tasks_popover.get_rows()
        expect(rows).to_have_count(3, timeout=_BUILD_TIMEOUT_MS)

        expect(rows.nth(0)).to_contain_text("Investigate the bug")
        expect(rows.nth(1)).to_contain_text("Write a failing test")
        expect(rows.nth(2)).to_contain_text("Implement the fix")

        # Verify completion status survived too.
        expect(get_plan_checkmark(plan_item=rows.nth(0))).to_have_count(1)
        expect(get_plan_checkmark(plan_item=rows.nth(1))).to_have_count(0)
        expect(get_plan_checkmark(plan_item=rows.nth(2))).to_have_count(0)
