"""Integration tests for the streaming cursor in alpha chat view.

Verifies that the blinking block cursor appears during agent turns (RUNNING)
and disappears once the agent finishes responding.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# Long streaming text streamed slowly to give time to observe the cursor mid-stream.
# With chunk_size=20 and delay_seconds=0.2, this takes ~40s to stream fully — plenty of
# buffer even on slow CI machines.
_STREAM_TEXT = "The streaming cursor should be visible while this text is being generated. " * 50


@user_story("to see a blinking cursor while the agent is streaming a response")
def test_streaming_cursor_visible_during_streaming(sculptor_instance_: SculptorInstance) -> None:
    """Test that the streaming cursor appears while the agent is actively streaming text."""
    page = sculptor_instance_.page

    # Create initial task and wait for completion
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:text `{"text": "Initial response."}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    # Send a slow-streaming message so we can observe the cursor mid-stream
    send_chat_message(
        chat_panel,
        f'fake_claude:stream_text `{{"text": "{_STREAM_TEXT}", "chunk_size": 20, "delay_seconds": 0.2}}`',
    )

    # Wait for streaming to start producing content
    text_blocks = alpha_view.get_text_blocks()
    expect(text_blocks.last).to_be_visible()

    # The streaming cursor should be visible during streaming
    cursor = alpha_view.get_streaming_cursor()
    expect(cursor.first).to_be_visible()

    # Wait for the streaming to finish and the cursor to disappear.
    # Wait directly for the cursor element to be removed.  The streaming takes
    # ~40s on fast machines, potentially longer on slow CI runners.
    expect(cursor).to_have_count(0, timeout=120_000)


@user_story("to see the cursor disappear when the agent completes a response")
def test_streaming_cursor_hidden_after_completion(sculptor_instance_: SculptorInstance) -> None:
    """Test that the streaming cursor is not present after a task completes."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:text `{"text": "Done with the task."}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    # No streaming cursor should be present after completion
    cursor = alpha_view.get_streaming_cursor()
    expect(cursor).to_have_count(0)


# A prompt that does tool use (bash) then streams text slowly, so we can
# verify cursor behavior across the tool→text transition.
_TOOL_THEN_STREAM_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {"command": "bash", "args": {"command": "echo hello"}},
    {"command": "stream_text", "args": {"text": "After the tool call, the cursor should appear here. ", "chunk_size": 15, "delay_seconds": 0.2, "repetitions": 20}}
  ]
}`"""


@user_story("to see the cursor appear during tool use and text streaming in the same turn")
def test_streaming_cursor_visible_during_tool_then_text(sculptor_instance_: SculptorInstance) -> None:
    """Test that the streaming cursor appears when agent does tool use then streams text."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:text `{"text": "Initial setup."}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    send_chat_message(chat_panel, _TOOL_THEN_STREAM_PROMPT)

    # Wait for text streaming to start
    text_blocks = alpha_view.get_text_blocks()
    expect(text_blocks.last).to_be_visible()

    # Cursor should be visible during streaming
    cursor = alpha_view.get_streaming_cursor()
    expect(cursor.first).to_be_visible()

    # Cursor should disappear after completion
    expect(cursor).to_have_count(0, timeout=120_000)


@user_story("to not see any cursor after sending multiple completed turns")
def test_streaming_cursor_absent_after_multiple_turns(sculptor_instance_: SculptorInstance) -> None:
    """Test that cursor is absent after multiple completed turns — no stale cursors."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:text `{"text": "First turn response."}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    # Send a second turn
    send_chat_message(chat_panel, 'fake_claude:text `{"text": "Second turn response."}`')
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()

    # Send a third turn
    send_chat_message(chat_panel, 'fake_claude:text `{"text": "Third turn response."}`')
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()

    # No cursor should be present anywhere
    cursor = alpha_view.get_streaming_cursor()
    expect(cursor).to_have_count(0)
