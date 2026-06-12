"""Integration test for the StatusPill stop-after-plan-acceptance bug.

Repro: the agent goes through plan mode, the user approves the plan, and the
agent starts working. The user clicks Stop once. The agent stops, but the
status pill ("thinking indicator") flickers back to a non-stopped active state
and stays visible indefinitely — only a second Stop click clears it.

After the fix, a single Stop click should make the status pill disappear.
"""

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.ask_user_question import get_ask_user_question_panel
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# Plan mode → exit_plan_mode (waits for approval) → long sleep so the agent is
# visibly busy after the user approves → final text. We never reach the final
# text in this test; the user interrupts during the sleep.
_PLAN_THEN_BUSY_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {"command": "enter_plan_mode"},
    {"command": "text", "args": {"text": "Here is my plan."}},
    {"command": "exit_plan_mode"},
    {"command": "sleep", "args": {"seconds": 60}},
    {"command": "text", "args": {"text": "All done."}}
  ]
}`"""


def _wait_for_approval_prompt(page: Page) -> None:
    ask_panel = get_ask_user_question_panel(page)
    expect(ask_panel).to_be_visible()


def _approve_plan(page: Page) -> None:
    ask_panel = get_ask_user_question_panel(page)
    ask_panel.select_option_by_text("Approve plan")
    ask_panel.submit()
    expect(ask_panel).not_to_be_visible()


@user_story("to stop the agent with one click after approving a plan")
def test_status_pill_disappears_after_single_stop_post_plan_approval(
    sculptor_instance_: SculptorInstance,
) -> None:
    """A single Stop click after plan approval must hide the status pill.

    Reproduces the bug where the pill flickers back to a thinking state and
    stays stuck until a second Stop click.
    """
    page = sculptor_instance_.page
    task_page = PlaywrightTaskPage(page=page)
    chat_panel = task_page.get_chat_panel()

    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=_PLAN_THEN_BUSY_PROMPT,
        wait_for_agent_to_finish=False,
    )

    _wait_for_approval_prompt(page)
    _approve_plan(page)

    # After approval the agent enters the sleep step — the pill should appear.
    status_pill = chat_panel.get_status_pill()
    expect(status_pill).to_be_visible()

    # Click Stop exactly once. We do not retry — this test is specifically
    # asserting that a single click is sufficient.
    stop_button = chat_panel.get_stop_button()
    expect(stop_button).to_be_visible()
    stop_button.click()

    # The pill must disappear without a second click. With the bug, the pill
    # transitions stopping → thinking and stays visible indefinitely.
    expect(status_pill).not_to_be_visible()
