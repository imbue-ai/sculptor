"""Integration tests for the new (alpha) chat view.

Tests that the new chat view correctly displays messages, text blocks,
tool calls, and supports switching to the debug view.

Also covers features ported from the classic view: AskUserQuestion rendering,
ExitPlanMode rendering, tool grouping with multiple tools, skill pills on
user messages, copy button on user messages, warning rendering, and
write_file (diff) tool results.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.alpha_chat_view import get_debug_chat_view
from sculptor.testing.elements.alpha_chat_view import switch_to_debug_view
from sculptor.testing.elements.ask_user_question import get_ask_user_question_block
from sculptor.testing.elements.ask_user_question import get_ask_user_question_panel
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.file_tree import get_file_tree
from sculptor.testing.playwright_utils import reset_active_panel_to_files
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# ---------------------------------------------------------------------------
# Plan-mode prompt used by ExitPlanMode tests
# ---------------------------------------------------------------------------

PLAN_MODE_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {"command": "enter_plan_mode"},
    {"command": "text", "args": {"text": "Here is the plan: modify files A, B, and C."}},
    {"command": "exit_plan_mode", "args": {"allowedPrompts": []}}
  ]
}`"""


# ---------------------------------------------------------------------------
# Alpha chat view feature tests (ported from classic view)
# ---------------------------------------------------------------------------


@user_story("to see ask-user-question blocks rendered in the new chat view")
def test_alpha_ask_user_question(sculptor_instance_: SculptorInstance) -> None:
    """AskUserQuestion block renders in the new chat view and can be answered."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "Which language?",
      "header": "Language",
      "options": [
        {"label": "Python", "description": "Versatile"},
        {"label": "Rust", "description": "Systems"}
      ],
      "multiSelect": false
    }
  ]
}`""",
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    ask_panel = get_ask_user_question_panel(page)
    expect(ask_panel).to_be_visible()

    ask_panel.select_option_by_text("Python")
    ask_panel.submit()
    expect(ask_panel).not_to_be_visible()

    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=60_000)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    ask_block = get_ask_user_question_block(page)
    expect(ask_block).to_be_visible()
    expect(ask_block).to_contain_text("Which language?")
    expect(ask_block).not_to_contain_text("DISMISSED")


@user_story("to see exit-plan-mode approval rendered in the new chat view")
def test_alpha_exit_plan_mode_approve(sculptor_instance_: SculptorInstance) -> None:
    """ExitPlanMode block renders in the new chat view after plan is approved."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=PLAN_MODE_PROMPT,
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    ask_panel = get_ask_user_question_panel(page)
    expect(ask_panel).to_be_visible()
    ask_panel.select_option_by_text("Approve plan")
    ask_panel.submit()

    expect(ask_panel).not_to_be_visible()
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=60_000)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    plan_block = alpha_view.get_exit_plan_mode_block()
    expect(plan_block).to_be_visible()
    expect(plan_block).to_contain_text("approved")


@user_story("to see multiple bash blocks rendered in the new chat view")
def test_alpha_tool_grouping(sculptor_instance_: SculptorInstance) -> None:
    """Multiple parallel bash tool calls render as individual bash blocks."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:multi_step `{
  "steps": [
    {"command": "parallel_tools", "args": {"tools": [
      {"tool_name": "Bash", "tool_input": {"command": "echo one"}},
      {"tool_name": "Bash", "tool_input": {"command": "echo two"}}
    ]}},
    {"command": "text", "args": {"text": "Done with both commands."}}
  ]
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    bash_blocks = alpha_view.get_bash_blocks()
    expect(bash_blocks).to_have_count(2)

    text_blocks = alpha_view.get_text_blocks()
    expect(text_blocks.last).to_contain_text("Done with both commands.")


@user_story("to see skill pills rendered on user messages in the new chat view")
def test_alpha_skill_pill(sculptor_instance_: SculptorInstance) -> None:
    """User messages starting with /command render as skill pills."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:text `{"text": "Skill response."}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    messages = alpha_view.get_messages()
    expect(messages).to_have_count(2)
    user_message = messages.first
    expect(user_message).to_contain_text("fake_claude")


@user_story("to see copy button on user messages in the new chat view")
def test_alpha_copy_button(sculptor_instance_: SculptorInstance) -> None:
    """User messages show a copy button on hover in the new chat view."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:text `{"text": "Copy test response."}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    copy_button = alpha_view.get_copy_buttons()
    expect(copy_button).to_be_attached()


@user_story("to see warning blocks rendered in the new chat view")
def test_alpha_warning_block(sculptor_instance_: SculptorInstance) -> None:
    """Warning messages from the agent render in the new chat view."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:warning `{"message": "Something looks off"}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    expect(alpha_view).to_contain_text("Something looks off")


@user_story("to see file write tool results as chips in the new chat view")
def test_alpha_write_file_tool(sculptor_instance_: SculptorInstance) -> None:
    """write_file tool calls render as chip rows in the new chat view."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:write_file `{
  "file_path": "alpha_test_file.txt",
  "content": "hello from alpha test"
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    chip_row = alpha_view.get_chip_rows()
    expect(chip_row).to_be_visible()

    file_chip = alpha_view.get_file_chips()
    expect(file_chip.first).to_be_visible()


@user_story("to see messages and text blocks in the new chat view")
def test_alpha_view_displays_messages(sculptor_instance_: SculptorInstance) -> None:
    """Test that the new chat view renders user and assistant messages with text content."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:text `{"text": "This is the assistant response."}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    messages = alpha_view.get_messages()
    expect(messages).to_have_count(2)

    text_blocks = alpha_view.get_text_blocks()
    expect(text_blocks).to_have_count(2)
    expect(text_blocks.last).to_contain_text("This is the assistant response.")


@user_story("to see tool calls displayed in the new chat view")
def test_alpha_view_displays_tool_calls(sculptor_instance_: SculptorInstance) -> None:
    """Test that tool calls are visible in the new chat view.

    Uses a multi_step FakeClaude command with a bash tool call followed by text.
    Bash commands render as dedicated bash blocks in the new chat view.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:multi_step `{
  "steps": [
    {"command": "bash", "args": {"command": "echo hello"}},
    {"command": "text", "args": {"text": "Done running the tools."}}
  ]
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    bash_block = alpha_view.get_bash_blocks()
    expect(bash_block.first).to_be_visible()

    text_blocks = alpha_view.get_text_blocks()
    expect(text_blocks.last).to_contain_text("Done running the tools.")


@user_story("to click file paths in assistant text to open the diff viewer")
def test_alpha_file_path_link(sculptor_instance_: SculptorInstance) -> None:
    """File paths in assistant text are clickable and open the diff viewer."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:multi_step `{
  "steps": [
    {"command": "write_file", "args": {"file_path": "src/example.py", "content": "print('hello')"}},
    {"command": "text", "args": {"text": "I updated src/example.py with the fix."}}
  ]
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    file_link = alpha_view.get_file_path_links()
    expect(file_link.first).to_be_visible()
    expect(file_link.first).to_contain_text("src/example.py")

    file_link.first.click()
    diff_panel = task_page.get_diff_panel()
    expect(diff_panel).to_be_visible()


@user_story("to see blocks in the debug chat view")
def test_debug_view_displays_blocks(sculptor_instance_: SculptorInstance) -> None:
    """Test that the debug view renders individual content blocks with type labels."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:text `{"text": "Debug view test response."}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    switch_to_debug_view(page)
    debug_view = get_debug_chat_view(page)
    expect(debug_view).to_be_visible()

    blocks = debug_view.get_blocks()
    expect(blocks.first).to_be_visible()
    expect(blocks.nth(1)).to_be_attached()


@user_story("to stay on the new chat view when the diff panel opens")
def test_alpha_view_persists_when_diff_panel_opens(sculptor_instance_: SculptorInstance) -> None:
    """Chat view mode should only change when the user clicks the toggle, not when the diff panel opens."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:write_file `{
  "file_path": "example.txt",
  "content": "hello world"
}`""",
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    reset_active_panel_to_files(page)
    file_tree = get_file_tree(page)
    row = file_tree.get_tree_rows().filter(has_text="example.txt")
    row.first.click()
    diff_panel = task_page.get_diff_panel()
    expect(diff_panel).to_be_visible()

    expect(alpha_view).to_be_visible()
