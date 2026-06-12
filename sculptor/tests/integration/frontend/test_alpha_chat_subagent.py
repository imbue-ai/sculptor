"""Integration tests for subagent (Agent tool) rendering in the alpha chat view.

Tests that Agent tool results are hidden from the chat UI — the user should only
see the subagent pill chip and the assistant's follow-up summary, not the raw
tool result content.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

SUBAGENT_RESULT = "Found 10 Python files in the repository."
SUMMARY_TEXT = "The subagent found 10 Python files."

SUBAGENT_PROMPT = f"""\
fake_claude:subagent `{{
  "description": "Find Python files",
  "prompt": "List all Python files",
  "subagent_result": "{SUBAGENT_RESULT}",
  "summary_text": "{SUMMARY_TEXT}"
}}`"""


@user_story("to verify that Agent tool results are hidden from the alpha chat view")
def test_subagent_tool_result_not_visible(sculptor_instance_: SculptorInstance) -> None:
    """Agent tool results should be hidden — only the subagent pill and summary text are visible."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=SUBAGENT_PROMPT,
    )
    chat_panel = task_page.get_chat_panel()
    # Wait for the agent to finish responding (thinking indicator gone).
    # The fake_claude:subagent handler produces multiple ChatMessages (main +
    # subagent + tool_result + summary), so rather than guessing the exact
    # count we just wait for the conversation to settle.
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    # The summary text should be visible (at least once).  Use expect() with a
    # generous timeout so that on slower CI runners the virtual list has time
    # to render all messages.
    text_blocks = alpha_view.get_text_blocks()
    expect(text_blocks.filter(has_text=SUMMARY_TEXT).first).to_be_visible(timeout=30_000)

    # The raw tool result content (Python repr format) should NOT be visible anywhere.
    # This is the raw format: [{'type': 'text', 'text': '...'}]
    raw_result_pattern = "{'type': 'text'"
    expect(alpha_view).not_to_contain_text(raw_result_pattern)


# SCU-1151: When the Agent tool is launched with run_in_background=true, the
# SDK emits an immediate tool_result containing internal book-keeping text:
#   "Async agent launched successfully.\nagentId: <subagent_msg_id>"
# That text is meant for the main agent only and must never surface in the UI
# as the subagent's response. The subagent's real reply arrives later, as a
# child message (parent_tool_use_id = the Agent's tool_use_id).
BG_SUBAGENT_RESULT = "Found 42 Python files in the repository."
BG_SUMMARY_TEXT = "The background subagent found 42 Python files."
BG_SUBAGENT_PROMPT = f"""\
fake_claude:background_subagent `{{
  "description": "Find Python files",
  "prompt": "List all Python files",
  "subagent_result": "{BG_SUBAGENT_RESULT}",
  "summary_text": "{BG_SUMMARY_TEXT}"
}}`"""


@user_story("to verify that a background Agent's launch-ack does not leak into the alpha chat view")
def test_background_subagent_launch_ack_not_visible(sculptor_instance_: SculptorInstance) -> None:
    """Background Agent launch-ack text must not leak as the subagent's response."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=BG_SUBAGENT_PROMPT,
    )
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    # The main agent's post-launch summary must be visible — proves the turn
    # actually finished, not that the test raced ahead.
    text_blocks = alpha_view.get_text_blocks()
    expect(text_blocks.filter(has_text=BG_SUMMARY_TEXT).first).to_be_visible(timeout=30_000)

    # The launch-ack is internal book-keeping. None of its tokens — the
    # "Async agent launched" prefix, or the leaked agentId — may appear
    # anywhere inside the alpha chat container.
    expect(alpha_view).not_to_contain_text("Async agent launched")
    expect(alpha_view).not_to_contain_text("agentId:")

    # The Agent tool_use must render as a subagent pill in the alpha view, with
    # the prompt visible — proves the message_conversion fix (giving each
    # cross-context turn its own ChatMessage ID) is in place. Without it, the
    # main agent message that carries the Agent tool_use collides with the
    # post-notification turn's ID and gets dropped from the visible chat,
    # taking the pill with it.
    pill = alpha_view.get_subagent_pills()
    expect(pill).to_have_count(1)
    expect(pill).to_contain_text("List all Python files")

    # The pill must STOP ticking once the subagent finishes. Real Claude (and
    # now FakeClaude, after we aligned `background_subagent` with the real
    # SDK behaviour) does not stream subagent content back to the parent —
    # only a task_notification arrives. Without consuming that notification
    # as the completion signal, `metadata.responseText` stays undefined and
    # `isThinking` stays true forever, so the elapsed-time display keeps
    # increasing. Sample the pill text twice with a delay between and assert
    # the displayed text is unchanged.
    text_t1 = pill.inner_text()
    page.wait_for_timeout(2_500)
    expect(pill).to_have_text(text_t1, use_inner_text=True)
