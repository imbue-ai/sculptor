"""Regression test: task list should survive even if the host-side cache is wiped.

Bug (SCU-1245): the host-side artifact cache (`task_sync_dir`) used to live
under `gettempdir()`. macOS's periodic jobs prune `$TMPDIR`, so a restart
after a prune surfaced an empty agent-tasks popover even though the
per-emit PLAN-* files in the workspace's stable artifacts dir were intact.

The fix has two parts: (1) move the cache somewhere stable (covered by the
unit test in sculptor/sculptor/config/test_settings.py), and (2) backfill
the cache from the workspace's stable artifacts dir when the cache file
is missing. This test exercises (2) end-to-end by deleting the entire
task_sync directory between Sculptor restarts and asserting the popover
still repopulates from the source-of-truth files.
"""

import shutil

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.plan_item import get_plan_checkmark
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

SECONDS_MS = 1000
_VISIBILITY_TIMEOUT_MS = 10 * SECONDS_MS
_BUILD_TIMEOUT_MS = 90 * SECONDS_MS


@user_story("to recover my agent's task list even after the host-side cache is wiped")
def test_task_list_survives_task_sync_dir_deletion(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """Task list items should reappear after restart even when task_sync is empty.

    Steps:
    1. Start a task that creates tasks via TaskCreate.
    2. Verify the tasks appear in the StatusPill popover.
    3. Shut down Sculptor (exit context).
    4. Delete the task_sync cache directory entirely, simulating an OS reap.
    5. Restart Sculptor against the same sculptor_folder and verify the tasks
       are still visible — proving the backfill from the workspace's stable
       artifacts dir works.
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

        sculptor_folder = instance.sculptor_folder

    # Wipe the task_sync cache while Sculptor is down. The per-emit PLAN-*
    # snapshots under the workspace's own artifacts dir are untouched, so a
    # correct backfill path will repopulate the popover on the next start.
    task_sync_dir = sculptor_folder / "internal" / "artifacts" / "task_sync"
    assert task_sync_dir.exists(), (
        f"Expected task_sync cache to exist after phase 1 at {task_sync_dir}; if the default location changed, update this test."
    )
    shutil.rmtree(task_sync_dir)

    with sculptor_instance_factory_.spawn_instance() as instance:
        workspace_tab = PlaywrightProjectLayoutPage(instance.page).get_workspace_tabs().first
        expect(workspace_tab).to_be_visible(timeout=_VISIBILITY_TIMEOUT_MS)
        workspace_tab.click()

        # Agents render as panel tabs in the center section now (PANEL_TAB-agent:<id>),
        # not the old AGENT_TAB strip. Reach the active agent's tab through the
        # agent-tab-bar shim and click it to focus the agent.
        task_page = PlaywrightTaskPage(page=instance.page)
        agent_tab = task_page.get_agent_tab_bar().get_agent_tabs().first
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
