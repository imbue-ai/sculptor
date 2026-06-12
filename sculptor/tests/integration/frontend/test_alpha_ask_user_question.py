"""Integration tests for the AskUserQuestion block in the alpha chat view.

The alpha view renders AskUserQuestion tool blocks as an inline component
(AlphaAskUserQuestionBlock) instead of the classic expandable tool block.
These tests verify the inline content (question text, selected options,
dismissed badge) is correct in the alpha view.

The Q&A *panel* interaction (selecting options, submitting) is identical
across views and is covered by ``test_ask_user_question.py``.  These tests
focus on the alpha-specific inline rendering after the question is resolved.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.ask_user_question import get_ask_user_question_block
from sculptor.testing.elements.ask_user_question import get_ask_user_question_panel
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import soft_reload_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# ========== Helpers ==========

_SINGLE_QUESTION_PROMPT = """\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "What language do you prefer?",
      "header": "Language",
      "options": [
        {"label": "Python", "description": "A versatile language"},
        {"label": "Rust", "description": "For systems programming"}
      ],
      "multiSelect": false
    }
  ]
}`"""

_COMMA_LABEL_PROMPT = """\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "Does this match your understanding?",
      "header": "Confirm",
      "options": [
        {"label": "Yes, proceed", "description": "The understanding is correct"},
        {"label": "No, revise", "description": "Please revise the approach"}
      ],
      "multiSelect": false
    }
  ]
}`"""

_MULTI_QUESTION_PROMPT = """\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "What language do you prefer?",
      "header": "Language",
      "options": [
        {"label": "Python", "description": "A versatile language"},
        {"label": "Rust", "description": "For systems programming"}
      ],
      "multiSelect": false
    },
    {
      "question": "What editor do you use?",
      "header": "Editor",
      "options": [
        {"label": "VS Code", "description": "Popular editor"},
        {"label": "Neovim", "description": "Terminal editor"}
      ],
      "multiSelect": false
    }
  ]
}`"""


# ========== Tests ==========


@user_story("to see the AUQ block in the alpha chat view after answering a question")
def test_alpha_auq_pill_shows_answered_summary(sculptor_instance_: SculptorInstance) -> None:
    """After answering a single question, the alpha view should show
    the question text and selected answer inline.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=_SINGLE_QUESTION_PROMPT,
        wait_for_agent_to_finish=False,
    )

    # Wait for the Q&A panel and answer the question
    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel).to_be_visible(timeout=30_000)
    auq_panel.select_first_option_and_submit()

    # Wait for agent to finish
    expect(task_page.get_thinking_indicator()).not_to_be_visible(timeout=30_000)

    # The AUQ block should be visible with inline content
    block = get_ask_user_question_block(page)
    expect(block).to_be_visible()

    # Block should show the question text and options
    expect(block).to_contain_text("What language do you prefer?")
    expect(block).to_contain_text("Python")
    expect(block).to_contain_text("Rust")


@user_story("to see the AUQ block pending state in the alpha chat view")
def test_alpha_auq_pill_pending_state(sculptor_instance_: SculptorInstance) -> None:
    """While a question is pending (no answers yet), the AUQ block should
    render as an empty element (no inline content visible).
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=_SINGLE_QUESTION_PROMPT,
        wait_for_agent_to_finish=False,
    )

    # Wait for the Q&A panel to appear (agent is waiting)
    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel).to_be_visible(timeout=30_000)

    # The AUQ block should be present but empty (no answers yet).
    # An empty div is considered "hidden" by Playwright, so check attached instead.
    block = get_ask_user_question_block(page)
    expect(block).to_be_attached()

    # Now answer the question to unblock the agent
    auq_panel.select_first_option_and_submit()
    expect(auq_panel).not_to_be_visible()


@user_story("to see the AUQ block dismissed state in the alpha chat view")
def test_alpha_auq_pill_dismissed_state(sculptor_instance_: SculptorInstance) -> None:
    """When a question is dismissed, the block should show a 'DISMISSED'
    badge and display the question with its options dimmed.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=_SINGLE_QUESTION_PROMPT,
        wait_for_agent_to_finish=False,
    )

    # Wait for the Q&A panel and dismiss
    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel).to_be_visible(timeout=30_000)
    auq_panel.dismiss()

    # Wait for agent to finish
    expect(task_page.get_thinking_indicator()).not_to_be_visible(timeout=30_000)

    # The block should show "DISMISSED" badge
    block = get_ask_user_question_block(page)
    expect(block).to_be_visible()
    expect(block).to_contain_text("DISMISSED")
    expect(block).to_contain_text("What language do you prefer?")


@user_story("to see the AUQ block with multiple questions in the alpha chat view")
def test_alpha_auq_pill_multiple_questions(sculptor_instance_: SculptorInstance) -> None:
    """With two questions, the block should show both Q&A pairs
    with their question text and options inline.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=_MULTI_QUESTION_PROMPT,
        wait_for_agent_to_finish=False,
    )

    # Wait for the Q&A panel
    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel).to_be_visible(timeout=30_000)

    # Answer question 1 (click first option, then "Next")
    auq_panel.get_options().first.click()
    submit_btn = auq_panel.get_submit_button()
    expect(submit_btn).to_have_text("Next")
    submit_btn.click()

    # Answer question 2 (click first option, then "Submit")
    auq_panel.get_options().first.click()
    expect(submit_btn).to_have_text("Submit")
    submit_btn.click()

    # Wait for agent to finish
    expect(task_page.get_thinking_indicator()).not_to_be_visible(timeout=30_000)

    # Block should show both questions
    block = get_ask_user_question_block(page)
    expect(block).to_be_visible()
    expect(block).to_contain_text("What language do you prefer?")
    expect(block).to_contain_text("What editor do you use?")


@user_story("to see the AUQ block persist in the alpha view after a page reload")
def test_alpha_auq_pill_persists_after_reload(sculptor_instance_: SculptorInstance) -> None:
    """After answering a question and reloading the page, the AUQ block
    should still be visible in the alpha view with the correct inline content.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=_SINGLE_QUESTION_PROMPT,
        wait_for_agent_to_finish=False,
    )

    # Answer the question
    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel).to_be_visible(timeout=30_000)
    auq_panel.select_first_option_and_submit()

    # Wait for agent to finish
    expect(task_page.get_thinking_indicator()).not_to_be_visible(timeout=30_000)

    # Verify block content before reload
    block = get_ask_user_question_block(page)
    expect(block).to_be_visible()
    expect(block).to_contain_text("What language do you prefer?")

    # Reload the page — alpha view config persists through the reload
    soft_reload_page(page)

    # Wait for the alpha view to re-render after reload
    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    # Block should still be visible with same content after reload
    block = get_ask_user_question_block(page)
    expect(block).to_be_visible()
    expect(block).to_contain_text("What language do you prefer?")


@user_story("to see the AUQ block alongside other tool calls in the alpha view")
def test_alpha_auq_pill_with_tool_calls(sculptor_instance_: SculptorInstance) -> None:
    """When the agent uses AskUserQuestion alongside other tools (like bash),
    the AUQ block should appear correctly in the alpha view tool section
    alongside the other tool blocks.
    """
    page = sculptor_instance_.page

    # First create a task where the agent does some work then asks a question.
    # Use multi_step: text → bash → then a follow-up with AUQ.
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="""\
fake_claude:multi_step `{
  "steps": [
    {"command": "bash", "args": {"command": "echo hello"}},
    {"command": "text", "args": {"text": "I need your input."}}
  ]
}`""",
    )

    # Wait for first turn to complete
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Now send a follow-up that triggers AUQ
    send_chat_message(chat_panel, _SINGLE_QUESTION_PROMPT)

    # Wait for Q&A panel and answer
    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel).to_be_visible(timeout=30_000)
    auq_panel.select_first_option_and_submit()

    expect(task_page.get_thinking_indicator()).not_to_be_visible(timeout=30_000)

    # The alpha view should have the AUQ block
    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    # AUQ block should be visible with the question text
    block = get_ask_user_question_block(page)
    expect(block).to_be_visible()
    expect(block).to_contain_text("What language do you prefer?")


@user_story("to see a selected option rendered correctly when its label contains a comma")
def test_alpha_auq_comma_in_option_label(sculptor_instance_: SculptorInstance) -> None:
    """When an option label contains a comma (e.g. 'Yes, proceed'), selecting
    it should highlight the option in the list — not render it as custom text.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=_COMMA_LABEL_PROMPT,
        wait_for_agent_to_finish=False,
    )

    # Wait for the Q&A panel and select the first option ("Yes, proceed")
    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel).to_be_visible(timeout=30_000)
    auq_panel.select_first_option_and_submit()

    # Wait for agent to finish
    expect(task_page.get_thinking_indicator()).not_to_be_visible(timeout=30_000)

    block = get_ask_user_question_block(page)
    expect(block).to_be_visible()

    # Bug: splitAnswerIntoParts splits "Yes, proceed" on ", " producing
    # ["Yes", "proceed"], neither matches an option label, so the answer
    # is rendered as custom text instead of highlighting the selected option.
    expect(block.get_custom_text()).not_to_be_attached()

    # The selected option should be marked as selected
    answered_options = block.get_answered_options()
    expect(answered_options).to_have_count(2)
    expect(answered_options.first).to_have_attribute("data-selected", "true")


@user_story("to see only one rendering of the AUQ block after answering — not also a generic tool-call card")
def test_alpha_auq_does_not_render_generic_tool_line_after_answer(sculptor_instance_: SculptorInstance) -> None:
    """After answering an AUQ, the alpha view should show ONLY the inline
    ``AlphaAskUserQuestionBlock`` for that question — not also a generic
    ``CompletedToolLine`` card for the matching ``mcp__sculptor__ask_user_question``
    tool_result.

    Regression for the observed bug where ``isTopLevelToolBlock`` promoted
    AUQ tool_result blocks into the topLevel bucket, causing a duplicate
    generic tool-call card to render alongside the special AUQ block.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=_SINGLE_QUESTION_PROMPT,
        wait_for_agent_to_finish=False,
    )

    # Wait for the Q&A panel and answer the question.
    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel).to_be_visible(timeout=30_000)
    auq_panel.select_first_option_and_submit()

    # Wait for the agent to finish so the tool_result is fully delivered.
    expect(task_page.get_thinking_indicator()).not_to_be_visible(timeout=30_000)

    # The AUQ block should be visible — that's the correct rendering.
    block = get_ask_user_question_block(page)
    expect(block).to_be_visible()

    # No generic tool-line cards should be rendered. ``_SINGLE_QUESTION_PROMPT``
    # triggers exactly one tool (the AUQ); FakeClaude follows up with text only.
    # The AUQ tool_result must NOT be rendered as a separate ``CompletedToolLine``
    # because the special block above already shows the answer.
    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view.get_tool_lines()).to_have_count(0)


@user_story("pressing ArrowUp while an AskUserQuestion panel is open does not hijack the key for prompt navigation")
def test_arrow_up_does_not_trigger_prompt_nav_when_ask_user_question_is_open(
    sculptor_instance_: SculptorInstance,
) -> None:
    """When the AskUserQuestion panel is visible, ArrowUp belongs to the panel
    (to move the focused option) — it must NOT be hijacked by the alpha
    prompt-navigation hook, which would otherwise scroll/highlight a previous
    prompt behind the panel.

    Repro: build a 2-prompt conversation (so prompt-nav has a valid target),
    then send a prompt that triggers an AUQ. With the bug, ArrowUp while the
    AUQ is showing adds the ``alphaPromptHighlight`` class to a prior message.
    After the fix, no highlight should appear.
    """
    page = sculptor_instance_.page

    # First turn: establish a prior user prompt so prompt-nav has a target to
    # decrement to when ArrowUp fires.
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:text `{"text": "First response."}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Second turn: trigger the AUQ. The agent pauses on the question; the AUQ
    # panel replaces the chat input and auto-focuses its container.
    send_chat_message(chat_panel, _SINGLE_QUESTION_PROMPT)
    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel).to_be_visible(timeout=30_000)

    # Press ArrowUp. With the bug, the window-level keydown listener in
    # useAlphaPromptNav fires in parallel with the AUQ panel's own onKeyDown,
    # enters navigation mode, and adds ``.alphaPromptHighlight`` to the
    # previous user prompt. With the fix, the hook short-circuits because
    # the AUQ panel is mounted.
    page.keyboard.press("ArrowUp")
    # Give the rAF-scheduled highlight a chance to apply, then assert it
    # never did. ``wait_for_function`` returns immediately when the condition
    # is true and throws a ``TimeoutError`` if a highlight ever appears —
    # giving a positive signal either way, unlike a bare assertion.
    page.wait_for_timeout(250)
    page.wait_for_function(
        "() => document.querySelectorAll('.alphaPromptHighlight').length === 0",
    )
