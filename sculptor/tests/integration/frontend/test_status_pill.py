"""Integration tests for the StatusPill component in the alpha chat view.

Tests that the StatusPill correctly appears during agent activity, shows
appropriate state labels, displays elapsed time, and disappears when done.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.ask_user_question import get_ask_user_question_panel
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import navigate_to_add_workspace_page
from sculptor.testing.playwright_utils import navigate_to_workspace
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# Use a bash sleep command so the agent stays busy long enough for the pill to appear.
SLOW_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {"command": "bash", "args": {"command": "sleep 30"}},
    {"command": "text", "args": {"text": "Done."}}
  ]
}`"""


@user_story("to see the status pill while the agent is working")
def test_status_pill_visible_during_agent_activity(sculptor_instance_: SculptorInstance) -> None:
    """Test that the status pill appears while the agent is streaming/working."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=SLOW_PROMPT,
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    status_pill = chat_panel.get_status_pill()
    expect(status_pill).to_be_visible()

    label = chat_panel.get_status_pill_label()
    expect(label).to_be_visible()
    expect(label).not_to_be_empty()

    elapsed = chat_panel.get_status_pill_elapsed()
    expect(elapsed).to_be_visible()
    expect(elapsed).to_contain_text("s")


@user_story("to see the status pill disappear after the agent finishes")
def test_status_pill_disappears_after_completion(sculptor_instance_: SculptorInstance) -> None:
    """Test that the status pill disappears once the agent is done."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:text `{"text": "Quick response."}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    status_pill = chat_panel.get_status_pill()
    expect(status_pill).not_to_be_visible()


@user_story("to see the stop button on the status pill while the agent is working")
def test_status_pill_shows_stop_button(sculptor_instance_: SculptorInstance) -> None:
    """Test that the stop button is present on the status pill during cancellable states."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=SLOW_PROMPT,
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    status_pill = chat_panel.get_status_pill()
    expect(status_pill).to_be_visible()

    # Stop button should be present in the DOM (always rendered for layout stability)
    stop_button = chat_panel.get_stop_button()
    expect(stop_button).to_be_attached()


@user_story("to see the status pill display an animation while the agent is active")
def test_status_pill_shows_animation(sculptor_instance_: SculptorInstance) -> None:
    """Test that the status pill shows an animation element while the agent is active."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=SLOW_PROMPT,
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    status_pill = chat_panel.get_status_pill()
    expect(status_pill).to_be_visible()

    animation = chat_panel.get_status_pill_animation()
    expect(animation).to_be_visible()


@user_story("to see the timer persist when switching workspace tabs and returning")
def test_status_pill_timer_persists_across_tab_switch(sculptor_instance_: SculptorInstance) -> None:
    """Timer should NOT reset when navigating away from a workspace and back.

    The StatusPill shows a running elapsed timer while the agent is working.
    When the user navigates to another page (e.g. Add Workspace) and returns
    by clicking the workspace tab, the timer should continue from where it
    was — not reset to 0.0s.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=SLOW_PROMPT,
        workspace_name="Timer Persist WS",
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Wait for the status pill to appear and the timer to reach at least 2s
    status_pill = chat_panel.get_status_pill()
    expect(status_pill).to_be_visible()

    elapsed_locator = chat_panel.get_status_pill_elapsed()
    page.wait_for_function(
        """() => {
            const el = document.querySelector('[data-testid="STATUS_PILL_ELAPSED"]');
            if (!el) return false;
            return parseFloat(el.textContent) >= 2.0;
        }""",
    )

    elapsed_before_text = elapsed_locator.text_content()
    assert elapsed_before_text is not None
    elapsed_before = float(elapsed_before_text.rstrip("s"))
    assert elapsed_before >= 2.0, f"Expected >= 2.0s before switch, got {elapsed_before}s"

    navigate_to_add_workspace_page(page)

    navigate_to_workspace(page)

    expect(status_pill).to_be_visible()

    # The timer should NOT have reset. On remount the timer is restored
    # synchronously from its persisted origin, so the FIRST non-zero value it
    # displays is already the continued time. A reset bug instead restarts at
    # 0.0s and ticks up from ~0.1s. Capturing that first non-zero value and
    # asserting it is already >= the pre-switch value distinguishes "continued"
    # from "reset" with no dependence on a timing margin — unlike a plain
    # ``>= threshold`` wait, which a reset-then-climb would eventually satisfy
    # (the agent keeps ticking) and thereby mask the regression.
    first_value_handle = page.wait_for_function(
        """() => {
            const el = document.querySelector('[data-testid="STATUS_PILL_ELAPSED"]');
            if (!el) return null;
            const value = parseFloat(el.textContent);
            return value > 0 ? value : null;
        }""",
    )
    first_value_after = first_value_handle.json_value()
    assert first_value_after >= elapsed_before - 0.5, (
        f"Timer reset on tab switch: first value after returning was {first_value_after}s,"
        + f" expected >= {elapsed_before - 0.5}s (continuing from {elapsed_before}s before the switch)."
        + " Expected the timer to resume, not restart from 0."
    )


@user_story("to not see a misleading 'Calling tools...' status pill while the AskUserQuestion panel is showing")
def test_status_pill_hidden_while_ask_user_question_panel_showing(sculptor_instance_: SculptorInstance) -> None:
    """While the AUQ panel is open, the alpha status pill must hide.

    Without this guard the pill reads "Calling tools..." (technically true —
    the MCP ``tools/call`` is still in flight, held by the in-process MCP
    server) but it's misleading because the agent is blocked on the user.
    The AUQ panel itself already conveys the "needs your input" state.

    The signal we gate on is ``TaskStatus === "WAITING"``, so this also
    covers the ExitPlanMode panel and plain plan-mode-without-AUQ cases.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "Which color do you prefer?",
      "header": "Color",
      "options": [
        {"label": "Red", "description": "A warm color"},
        {"label": "Blue", "description": "A cool color"}
      ],
      "multiSelect": false
    }
  ]
}`""",
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Wait for the AUQ panel to appear — confirms the agent is in the
    # WAITING state with a held MCP tools/call.
    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel).to_be_visible()

    status_pill = chat_panel.get_status_pill()
    expect(status_pill).not_to_be_visible()
