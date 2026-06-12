"""Integration tests for the agent-tasks UI (StatusPill popover).

The agent-tasks UI lives in the StatusPill popover (the legacy
``TodoListPanel`` was deprecated). These tests verify that TaskCreate /
TaskUpdate calls produced by the agent surface in the popover and update as
the agent reports completion.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.agent_tasks_popover import PlaywrightAgentTasksPopoverElement
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.plan_item import get_plan_checkmark
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to see the plan that agent defined for itself")
def test_plans_show_up_in_tasks_popover(sculptor_instance_: SculptorInstance) -> None:
    """TaskCreate calls surface in the StatusPill tasks popover."""

    task_page = start_task_and_wait_for_ready(
        sculptor_instance_.page,
        prompt="""\
fake_claude:multi_step `{
  "steps": [
    {"command": "task_create", "args": {"id": "1", "subject": "Step 1", "status": "in_progress", "activeForm": "Working on Step 1"}},
    {"command": "task_create", "args": {"id": "2", "subject": "Step 2", "status": "pending", "activeForm": "Working on Step 2"}}
  ]
}`""",
        wait_for_agent_to_finish=False,
    )

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    popover = PlaywrightAgentTasksPopoverElement(sculptor_instance_.page)
    popover.open()

    rows = popover.get_rows()
    expect(rows).to_have_count(2)
    expect(rows.nth(0)).to_contain_text("Step 1")
    expect(rows.nth(1)).to_contain_text("Step 2")


@user_story("to see the plan that agent defined for itself")
def test_plans_update_with_completion(sculptor_instance_: SculptorInstance) -> None:
    """TaskUpdate calls from a follow-up turn flow into the popover."""

    task_page = start_task_and_wait_for_ready(
        sculptor_instance_.page,
        prompt="""\
fake_claude:multi_step `{
  "steps": [
    {"command": "task_create", "args": {"id": "1", "subject": "Step 1", "status": "in_progress", "activeForm": "Working on Step 1"}},
    {"command": "task_create", "args": {"id": "2", "subject": "Step 2", "status": "pending", "activeForm": "Working on Step 2"}},
    {"command": "task_create", "args": {"id": "3", "subject": "Step 3", "status": "pending", "activeForm": "Working on Step 3"}}
  ]
}`""",
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    popover = PlaywrightAgentTasksPopoverElement(sculptor_instance_.page)
    popover.open()
    rows = popover.get_rows()
    expect(rows).to_have_count(3, timeout=60_000)
    expect(get_plan_checkmark(plan_item=rows.nth(0))).to_have_count(0)
    expect(get_plan_checkmark(plan_item=rows.nth(1))).to_have_count(0)
    expect(get_plan_checkmark(plan_item=rows.nth(2))).to_have_count(0)

    send_chat_message(
        chat_panel=chat_panel,
        message="""\
fake_claude:multi_step `{
  "steps": [
    {"command": "task_update", "args": {"id": "1", "status": "completed"}},
    {"command": "task_update", "args": {"id": "2", "status": "completed"}}
  ]
}`""",
    )
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # Sending the follow-up message clicks the chat input — outside the
    # popover — which dismisses the pinned popover. Re-open it to inspect
    # the updated tasks.
    popover.open()

    expect(rows).to_have_count(3)
    expect(get_plan_checkmark(plan_item=rows.nth(0))).to_have_count(1)
    expect(get_plan_checkmark(plan_item=rows.nth(1))).to_have_count(1)
    expect(get_plan_checkmark(plan_item=rows.nth(2))).to_have_count(0)
