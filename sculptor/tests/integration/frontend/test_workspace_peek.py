"""Integration tests for the workspace peek popover feature.

Tests cover:
- Popover appears on workspace tab hover with correct status content
- Idle state shows popover with workspace name, summary, and agent row (no banner)
- Waiting state shows orange waiting banner when agent asks a question
- Hover mechanics: popover appears on hover and dismisses on mouse leave
"""

from playwright.sync_api import expect

from sculptor.testing.elements.ask_user_question import get_ask_user_question_panel
from sculptor.testing.elements.chat_panel import select_model_by_name
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.task_starter import FAKE_CLAUDE_MODEL_NAME
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import navigate_to_add_workspace_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to see workspace peek status when hovering over a workspace tab with a finished agent")
def test_workspace_peek_popover_idle_state(
    sculptor_instance_: SculptorInstance,
) -> None:
    """After an agent finishes its turn, hovering the workspace tab shows a
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

    # Navigate away so we can hover over the workspace tab
    navigate_to_add_workspace_page(page)

    workspace_tab = layout.get_workspace_tabs().first
    workspace_tab.hover()

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
    """When an agent invokes AskUserQuestion, hovering the workspace tab shows
    a popover with an orange waiting banner.
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

    # Navigate away so we can hover over the workspace tab
    navigate_to_add_workspace_page(page)

    workspace_tab = layout.get_workspace_tabs().first
    workspace_tab.hover()

    peek = layout.get_workspace_peek_popover()
    expect(peek).to_be_visible()

    expect(peek.get_header()).to_contain_text("Waiting WS")

    expect(peek.get_banner()).to_be_visible()
    expect(peek.get_banner()).to_contain_text("needs your input")


@user_story("to quickly glance at workspace status by hovering over its tab")
def test_workspace_peek_popover_hover_mechanics(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Hovering over a workspace tab shows the popover; moving the mouse
    away dismisses it. The popover contains a header, agent rows, and footer.
    """
    page = sculptor_instance_.page
    layout = PlaywrightProjectLayoutPage(page=page)

    start_task_and_wait_for_ready(
        page,
        prompt='fake_claude:text `{"text": "Done"}`',
        workspace_name="Hover WS",
    )

    # Navigate away so we can hover over the workspace tab
    navigate_to_add_workspace_page(page)

    workspace_tab = layout.get_workspace_tabs().first
    peek = layout.get_workspace_peek_popover()

    expect(peek).to_be_hidden()

    workspace_tab.hover()
    expect(peek).to_be_visible()

    expect(peek.get_header()).to_be_visible()
    expect(peek.get_agent_rows().first).to_be_visible()

    # Move to the top-left corner which is far from the tab.
    page.mouse.move(0, 0)
    expect(peek).to_be_hidden()


@user_story("to see workspace peek status when hovering over a scrolled-into-view workspace tab")
def test_workspace_peek_popover_on_scrolled_tab(
    sculptor_instance_: SculptorInstance,
) -> None:
    """When the viewport is narrow enough that workspace tabs overflow into a
    horizontal scroll area, scrolling a tab into view and hovering it should
    still show the peek popover.
    """
    page = sculptor_instance_.page
    layout = PlaywrightProjectLayoutPage(page=page)

    # Create 3 workspaces so there are enough tabs to overflow a narrow viewport.
    for i in range(3):
        start_task_and_wait_for_ready(
            sculptor_page=page,
            prompt='fake_claude:text `{"text": "Done"}`',
            workspace_name=f"WS {i + 1}",
        )

    # Navigate away so we're not on any workspace tab
    navigate_to_add_workspace_page(page)

    # Shrink viewport to force tab overflow (3 workspace tabs + "Open Workspace"
    # tab at 200px each = 800px, which won't fit in a 780px-wide viewport).
    # Must stay ABOVE the 768px mobile breakpoint: below it the mobile shell
    # replaces the workspace tab strip entirely and there is no tab to hover.
    original_size = page.viewport_size
    page.set_viewport_size({"width": 780, "height": original_size["height"]})

    # "WS 1" is the leftmost tab, which may be scrolled out of view.
    # Scroll it into view and hover to trigger the peek popover.
    ws1_tab = layout.get_workspace_tabs().filter(has_text="WS 1")
    ws1_tab.scroll_into_view_if_needed()
    ws1_tab.hover()

    peek = layout.get_workspace_peek_popover()
    expect(peek).to_be_visible()

    # Restore viewport
    page.set_viewport_size(original_size)


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

    # Add a second agent to the same workspace
    agent_tab_bar = task_page.get_agent_tab_bar()
    add_agent_button = agent_tab_bar.get_add_agent_button()
    expect(add_agent_button).to_be_visible()
    add_agent_button.click()

    # The new blank agent needs a model selected before it can receive messages
    chat_panel = task_page.get_chat_panel()
    select_model_by_name(chat_panel, FAKE_CLAUDE_MODEL_NAME)

    # Send an AUQ prompt to the second agent so it enters WAITING state
    send_chat_message(chat_panel, _AUQ_PROMPT)

    # Wait for the AUQ panel to appear, confirming the agent is in WAITING state
    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel).to_be_visible()

    # Navigate away so the workspace tab is hoverable
    navigate_to_add_workspace_page(page)

    workspace_tab = task_page.get_workspace_tabs().first
    workspace_tab.hover()

    peek = task_page.get_workspace_peek_popover()
    expect(peek).to_be_visible()

    # The banner must surface the waiting agent — attention takes priority over
    # a still-running agent.
    expect(peek.get_banner()).to_be_visible()
    expect(peek.get_banner()).to_contain_text("needs your")


@user_story("to see diff stats in the workspace peek popover")
def test_peek_popover_shows_diff_stats(sculptor_instance_: SculptorInstance) -> None:
    """Hovering over the workspace tab should show a popover with
    target-branch diff stats (+N / -N)."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        page,
        prompt='fake_claude:write_file `{"file_path": "hello.py", "content": "print(\'hello\')"}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    workspace_tab = task_page.get_workspace_tabs().first
    expect(workspace_tab).to_be_visible()
    workspace_tab.hover()

    peek = task_page.get_workspace_peek_popover()
    expect(peek).to_be_visible()

    footer = peek.get_footer()
    expect(footer).to_be_visible()
    expect(footer).to_contain_text("+")
