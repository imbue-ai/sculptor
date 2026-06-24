"""Integration tests for the workspace peek popover feature.

The peek popover now follows the hovered workspace **row** in the sidebar (it
used to follow the workspace tab); its content and behaviour are unchanged.

Tests cover:
- Popover appears on workspace-row hover with correct status content
- Idle state shows popover with workspace name, summary, and agent row (no banner)
- Waiting state shows the attention banner when an agent asks a question
- Hover mechanics: popover appears on hover and dismisses on mouse leave
- Diff stats appear in the popover footer
"""

from playwright.sync_api import expect

from sculptor.testing.elements.add_panel_dropdown import create_agent_panel
from sculptor.testing.elements.ask_user_question import get_ask_user_question_panel
from sculptor.testing.elements.chat_panel import select_model_by_name
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.task_starter import FAKE_CLAUDE_MODEL_NAME
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to see workspace peek status when hovering over a workspace row with a finished agent")
def test_workspace_peek_popover_idle_state(
    sculptor_instance_: SculptorInstance,
) -> None:
    """After an agent finishes its turn, hovering the workspace row shows a
    popover with the workspace name, a summary, and an agent row.  No alert
    banner is shown because the agent is idle (ready for more input).
    """
    page = sculptor_instance_.page
    layout = PlaywrightProjectLayoutPage(page=page)

    start_task_and_wait_for_ready(
        page,
        prompt='fake_claude:text `{"text": "All done!"}`',
        workspace_name="Idle WS",
    )

    workspace_row = get_workspace_sidebar(page).get_workspace_rows().first
    workspace_row.hover()

    peek = layout.get_workspace_peek_popover()
    expect(peek).to_be_visible()

    expect(peek.get_header()).to_contain_text("Idle WS")

    # No alert banner for idle state
    expect(peek.get_banner()).to_be_hidden()

    expect(peek.get_agent_rows().first).to_be_visible()


@user_story("to see workspace peek waiting status when an agent asks a question")
def test_workspace_peek_popover_waiting_state(
    sculptor_instance_: SculptorInstance,
) -> None:
    """When an agent invokes AskUserQuestion, hovering the workspace row shows
    a popover with the attention/waiting banner.
    """
    page = sculptor_instance_.page
    layout = PlaywrightProjectLayoutPage(page=page)

    # Create a workspace where the agent asks a question.  AUQ prompts leave
    # the agent in WAITING state rather than completing the turn, so don't
    # wait for the agent to "finish" — wait for the AUQ panel directly as the
    # signal that the response has rendered.
    start_task_and_wait_for_ready(
        page,
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
        workspace_name="Waiting WS",
        wait_for_agent_to_finish=False,
    )

    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel).to_be_visible(timeout=30_000)

    workspace_row = get_workspace_sidebar(page).get_workspace_rows().first
    workspace_row.hover()

    peek = layout.get_workspace_peek_popover()
    expect(peek).to_be_visible()

    expect(peek.get_header()).to_contain_text("Waiting WS")

    expect(peek.get_banner()).to_be_visible()
    expect(peek.get_banner()).to_contain_text("needs your input")


@user_story("to quickly glance at workspace status by hovering over its sidebar row")
def test_workspace_peek_popover_hover_mechanics(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Hovering over a workspace row shows the popover; moving the mouse
    away dismisses it. The popover contains a header and agent rows.
    """
    page = sculptor_instance_.page
    layout = PlaywrightProjectLayoutPage(page=page)

    start_task_and_wait_for_ready(
        page,
        prompt='fake_claude:text `{"text": "Done"}`',
        workspace_name="Hover WS",
    )

    workspace_row = get_workspace_sidebar(page).get_workspace_rows().first
    peek = layout.get_workspace_peek_popover()

    expect(peek).to_be_hidden()

    workspace_row.hover()
    expect(peek).to_be_visible()

    expect(peek.get_header()).to_be_visible()
    expect(peek.get_agent_rows().first).to_be_visible()

    # Move to the top-left corner which is far from the row.
    page.mouse.move(0, 0)
    expect(peek).to_be_hidden()


_AUQ_PROMPT = """\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "Which approach do you prefer?",
      "header": "Approach",
      "options": [
        {"label": "Option A", "description": "First option"},
        {"label": "Option B", "description": "Second option"}
      ],
      "multiSelect": false
    }
  ]
}`"""


@user_story("to see the workspace status turn yellow when any agent needs my attention")
def test_workspace_peek_waiting_overrides_running_in_banner(
    sculptor_instance_: SculptorInstance,
) -> None:
    """When one agent is running and another is waiting for user input, the
    peek popover should surface the waiting state via the attention banner,
    even though another agent is still running.
    """
    page = sculptor_instance_.page
    task_page = PlaywrightTaskPage(page=page)

    # Create a workspace with a first agent that stays running (sleeping)
    start_task_and_wait_for_ready(
        page,
        prompt='fake_claude:sleep `{"seconds": 60}`',
        workspace_name="Running+Waiting WS",
        wait_for_agent_to_finish=False,
    )

    # Add a second agent to the same workspace (lands in the center section).
    create_agent_panel(page, section="center")

    # The new blank agent needs a model selected before it can receive messages
    chat_panel = task_page.get_chat_panel()
    select_model_by_name(chat_panel, FAKE_CLAUDE_MODEL_NAME)

    # Send an AUQ prompt to the second agent so it enters WAITING state
    send_chat_message(chat_panel, _AUQ_PROMPT)

    # Wait for the AUQ panel to appear, confirming the agent is in WAITING state
    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel).to_be_visible()

    workspace_row = get_workspace_sidebar(page).get_workspace_rows().first
    workspace_row.hover()

    peek = task_page.get_workspace_peek_popover()
    expect(peek).to_be_visible()

    # The banner must surface the waiting agent — attention takes priority over
    # a still-running agent.
    expect(peek.get_banner()).to_be_visible()
    expect(peek.get_banner()).to_contain_text("needs your")


@user_story("to see diff stats in the workspace peek popover")
def test_peek_popover_shows_diff_stats(sculptor_instance_: SculptorInstance) -> None:
    """Hovering over the workspace row should show a popover with
    target-branch diff stats (+N / -N)."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        page,
        prompt='fake_claude:write_file `{"file_path": "hello.py", "content": "print(\'hello\')"}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    workspace_row = get_workspace_sidebar(page).get_workspace_rows().first
    expect(workspace_row).to_be_visible()
    workspace_row.hover()

    peek = task_page.get_workspace_peek_popover()
    expect(peek).to_be_visible()

    footer = peek.get_footer()
    expect(footer).to_be_visible()
    expect(footer).to_contain_text("+")
