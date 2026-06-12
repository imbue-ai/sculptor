"""Real Claude integration tests: interrupt scenarios.

These are the **critical tests** for the stdin control protocol branch.
Each verifies that the stdin interrupt protocol works and that --resume
preserves full conversation context (no amnesia).
"""

import re

import pytest
from playwright.sync_api import expect

from sculptor.testing.elements.ask_user_question import get_ask_user_question_panel
from sculptor.testing.sculptor_instance import SculptorInstance
from tests.integration.real_claude.helpers import RESPONSE_TIMEOUT_MS
from tests.integration.real_claude.helpers import _get_assistant_messages
from tests.integration.real_claude.helpers import assert_any_message_contains
from tests.integration.real_claude.helpers import assert_interrupted
from tests.integration.real_claude.helpers import assert_last_message_contains
from tests.integration.real_claude.helpers import assert_no_errors
from tests.integration.real_claude.helpers import assert_transcript_contains
from tests.integration.real_claude.helpers import assert_transcript_turn_count
from tests.integration.real_claude.helpers import create_workspace_and_send
from tests.integration.real_claude.helpers import get_transcript_path
from tests.integration.real_claude.helpers import interrupt_agent
from tests.integration.real_claude.helpers import interrupt_and_send
from tests.integration.real_claude.helpers import read_transcript
from tests.integration.real_claude.helpers import real_claude
from tests.integration.real_claude.helpers import send_and_wait
from tests.integration.real_claude.helpers import send_no_wait
from tests.integration.real_claude.helpers import wait_for_any_assistant_text
from tests.integration.real_claude.helpers import wait_for_streaming_text

# ---------------------------------------------------------------------------
# THE MOST IMPORTANT TEST: Interrupt during streaming, no amnesia
# ---------------------------------------------------------------------------


@real_claude
@pytest.mark.timeout(300)
def test_interrupt_during_streaming_no_amnesia(sculptor_instance_: SculptorInstance) -> None:
    """Core amnesia prevention test.

    This is the single most important test — it directly validates that the
    stdin interrupt protocol produces a clean transcript that --resume can read.
    """
    task_page = create_workspace_and_send(
        sculptor_instance_,
        "Remember this code: ANCHOR-WHISKEY-39201. Reply with exactly: ANCHOR-STORED.",
    )
    chat_panel = task_page.get_chat_panel()
    assert_last_message_contains(chat_panel, "ANCHOR-STORED")

    # Start a long essay (gives us time to interrupt mid-stream)
    send_no_wait(
        chat_panel,
        (
            "Write a very long, detailed essay about the history of the internet. It must be at least 2000 words. Start your essay with ESSAY-BEGINS-HERE: and number each paragraph."
        ),
    )

    # Wait for streaming to begin, then interrupt
    wait_for_streaming_text(chat_panel, "ESSAY-BEGINS-HERE")
    interrupt_agent(chat_panel)
    assert_interrupted(chat_panel)

    # THE CRITICAL CHECK: Does the agent remember the anchor code?
    send_and_wait(
        chat_panel,
        "What is the code I asked you to remember at the start of our conversation? Reply in the format: RECALLED-CODE: <code>",
    )
    assert_last_message_contains(chat_panel, "ANCHOR-WHISKEY-39201")

    # TRANSCRIPT VERIFICATION: confirm the initial anchor exchange is properly
    # recorded in the Claude session file, proving the interrupt didn't corrupt
    # the transcript. If this fails while the UI assertion above passes, it
    # means the agent is hallucinating from context — the transcript is broken.
    transcript_path = get_transcript_path(sculptor_instance_, task_page)
    transcript = read_transcript(transcript_path)
    assert_transcript_contains(transcript, "ANCHOR-WHISKEY-39201", role="user")
    assert_transcript_contains(transcript, "ANCHOR-STORED", role="assistant")
    # NOTE: We do NOT assert the interrupted essay content is in the transcript.
    # The CLI may not flush partial assistant responses for interrupted turns.
    # The critical check is that the pre-interrupt context (anchor) is preserved.
    # At least 3 user turns: anchor, essay request, recall question
    assert_transcript_turn_count(transcript, "user", min_count=3)


# ---------------------------------------------------------------------------
# Interrupt during tool execution, no amnesia
# ---------------------------------------------------------------------------


@real_claude
@pytest.mark.timeout(300)
def test_interrupt_during_tool_execution_no_amnesia(sculptor_instance_: SculptorInstance) -> None:
    """Verify interrupt during an active tool call preserves context."""
    task_page = create_workspace_and_send(
        sculptor_instance_,
        (
            "Use the Write tool to create 'anchor-tool.txt' with content 'TOOL-ANCHOR-88312'. Then reply with: TOOL-ANCHOR-SAVED."
        ),
    )
    chat_panel = task_page.get_chat_panel()
    assert_last_message_contains(chat_panel, "TOOL-ANCHOR-SAVED")

    # Start a long bash sleep (agent will be in a tool call)
    send_no_wait(
        chat_panel,
        "Use the Bash tool to run: sleep 120. Do not add any commentary.",
    )

    # Wait for the thinking indicator (tool call has started)
    expect(chat_panel.get_thinking_indicator()).to_be_visible(timeout=30_000)

    interrupt_agent(chat_panel)
    assert_interrupted(chat_panel)

    # Verify memory
    send_and_wait(
        chat_panel,
        "What file did you create earlier and what was its content? Reply starting with: TOOL-RECALL:",
    )
    assert_last_message_contains(chat_panel, "anchor-tool.txt")
    assert_last_message_contains(chat_panel, "TOOL-ANCHOR-88312")


# ---------------------------------------------------------------------------
# Multiple interrupts, no amnesia
# ---------------------------------------------------------------------------


@real_claude
@pytest.mark.timeout(300)
def test_multiple_interrupts_no_amnesia(sculptor_instance_: SculptorInstance) -> None:
    """Verify memory survives multiple interrupt/resume cycles.

    Uses a message-counting approach: after two interrupted essay requests,
    asks Claude how many messages it received. This tests conversation context
    integrity without relying on recall of a specific value, which is sensitive
    to LLM attention issues in noisy interrupt transcripts.
    """
    task_page = create_workspace_and_send(
        sculptor_instance_,
        "This is message 1. Reply with exactly: MSG-1-ACK",
    )
    chat_panel = task_page.get_chat_panel()
    assert_last_message_contains(chat_panel, "MSG-1-ACK")

    # First interrupt (message 2)
    send_no_wait(
        chat_panel,
        "This is message 2. Write a 2000-word essay about dogs. Start with: DOG-ESSAY-START:",
    )
    wait_for_streaming_text(chat_panel, "DOG-ESSAY-START")
    interrupt_agent(chat_panel)
    assert_interrupted(chat_panel)

    # Second interrupt (message 3)
    send_no_wait(
        chat_panel,
        "This is message 3. Write a 2000-word essay about cats. Start with: CAT-ESSAY-START:",
    )
    wait_for_streaming_text(chat_panel, "CAT-ESSAY-START")
    interrupt_agent(chat_panel)
    assert_interrupted(chat_panel)

    # Message 4: ask Claude to count messages
    send_and_wait(
        chat_panel,
        (
            "This is message 4. How many messages have I sent you in this conversation? "
            "Count only my messages (not yours or system messages). "
            "Reply in the format: MESSAGE-COUNT: <number>"
        ),
    )

    # Read the last *assistant* message, not the last message overall.
    # In alpha view both user and assistant share the ALPHA_CHAT_MESSAGE
    # testid, so ``get_messages().last`` returned the user prompt — making
    # the MESSAGE-COUNT regex miss and the assertion fail spuriously.
    assistant_messages = _get_assistant_messages(chat_panel)
    expect(assistant_messages.last).to_contain_text("MESSAGE-COUNT:")
    last_text = assistant_messages.last.inner_text()

    # Claude should report 4 messages. We accept 3-5 to allow for minor
    # counting differences (e.g. whether interrupt notifications count).
    # The key check is that it's NOT 1 or 2 (which would mean context loss).
    match = re.search(r"MESSAGE-COUNT:\s*(\d+)", last_text)
    assert match, f"Expected MESSAGE-COUNT: <number> in response, got: {last_text[:300]}"
    count = int(match.group(1))
    assert count >= 3, (  # noqa: PLR2004
        f"Claude reported only {count} messages — context was lost after interrupts. "
        f"Expected at least 3 (sent 4). Response: {last_text[:300]}"
    )

    # TRANSCRIPT VERIFICATION: confirm the conversation structure is intact.
    transcript_path = get_transcript_path(sculptor_instance_, task_page)
    transcript = read_transcript(transcript_path)
    assert_transcript_contains(transcript, "MSG-1-ACK", role="assistant")
    # At least 4 user turns: msg1, dog essay, cat essay, count question
    assert_transcript_turn_count(transcript, "user", min_count=4)


# ---------------------------------------------------------------------------
# Rapid stop (interrupt very early in streaming)
# ---------------------------------------------------------------------------


@real_claude
@pytest.mark.timeout(300)
def test_interrupt_early_streaming(sculptor_instance_: SculptorInstance) -> None:
    """Verify very early interrupts work (text has barely started)."""
    task_page = create_workspace_and_send(
        sculptor_instance_,
        ("Write a 5000-word essay about quantum physics. Start with: QUANTUM-BEGINS-HERE:"),
        wait_for_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Interrupt as soon as any text appears
    wait_for_any_assistant_text(chat_panel)
    interrupt_agent(chat_panel)
    assert_interrupted(chat_panel)
    assert_no_errors(chat_panel)

    # Verify recovery
    send_and_wait(chat_panel, "Reply with exactly: RAPID-STOP-RECOVERED-OK")
    assert_last_message_contains(chat_panel, "RAPID-STOP-RECOVERED-OK")


# ---------------------------------------------------------------------------
# Immediate stop before any output
# ---------------------------------------------------------------------------


@real_claude
@pytest.mark.timeout(300)
def test_interrupt_before_any_output(sculptor_instance_: SculptorInstance) -> None:
    """Verify stopping before the session ID is written doesn't crash."""
    task_page = create_workspace_and_send(
        sculptor_instance_,
        "Write an extremely detailed 10000-word essay about every planet in the solar system.",
        wait_for_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Wait just for the thinking indicator, then immediately stop
    expect(chat_panel.get_thinking_indicator()).to_be_visible(timeout=30_000)
    interrupt_agent(chat_panel)

    # No crash, no InterruptFailure
    messages = chat_panel.get_messages()
    expect(messages.filter(has_text="InterruptFailure")).to_have_count(0)

    assert_no_errors(chat_panel)

    # Verify recovery
    send_and_wait(chat_panel, "Reply with exactly: IMMEDIATE-STOP-OK-55023")
    assert_last_message_contains(chat_panel, "IMMEDIATE-STOP-OK-55023")


# ---------------------------------------------------------------------------
# Interrupt and continue with complex multi-step work
# ---------------------------------------------------------------------------


@real_claude
@pytest.mark.timeout(300)
def test_interrupt_and_continue_with_tools(sculptor_instance_: SculptorInstance) -> None:
    """After interrupt, agent can do complex multi-step work."""
    task_page = create_workspace_and_send(
        sculptor_instance_,
        "Write a 3000-word essay about volcanoes. Start with VOLCANO-START:",
        wait_for_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    wait_for_streaming_text(chat_panel, "VOLCANO-START")
    interrupt_agent(chat_panel)

    # Now do real multi-step work
    send_and_wait(
        chat_panel,
        (
            "Do these steps:\n1. Use Write to create 'post-interrupt.txt' with content 'RECOVERED-SENTINEL-20398'\n2. Use Bash to run: cat post-interrupt.txt\n3. Reply with: ALL-POST-INTERRUPT-STEPS-DONE"
        ),
    )
    assert_last_message_contains(chat_panel, "ALL-POST-INTERRUPT-STEPS-DONE")
    assert_no_errors(chat_panel)


# ---------------------------------------------------------------------------
# Queue message + "Interrupt and send"
# ---------------------------------------------------------------------------


@real_claude
@pytest.mark.timeout(300)
def test_queue_and_interrupt_and_send(sculptor_instance_: SculptorInstance) -> None:
    """Verify the 'interrupt and send' flow works with stdin protocol."""
    task_page = create_workspace_and_send(
        sculptor_instance_,
        "Write a 3000-word essay about ocean life. Start with OCEAN-ESSAY-START:",
        wait_for_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Wait for streaming to begin
    wait_for_streaming_text(chat_panel, "OCEAN-ESSAY-START")

    # Type a new message and click send (which acts as "interrupt and send")
    interrupt_and_send(
        chat_panel,
        task_page._page,
        "Stop writing. Reply with exactly: INTERRUPT-SEND-SENTINEL-40182",
    )

    # Wait for the new response
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=RESPONSE_TIMEOUT_MS)
    assert_any_message_contains(chat_panel, "INTERRUPT-SEND-SENTINEL-40182")


# ---------------------------------------------------------------------------
# Queue + interrupt and send, memory preserved
# ---------------------------------------------------------------------------


@real_claude
@pytest.mark.timeout(300)
def test_interrupt_and_send_memory_preserved(sculptor_instance_: SculptorInstance) -> None:
    """Verify interrupt-and-send preserves conversation history."""
    task_page = create_workspace_and_send(
        sculptor_instance_,
        "Remember: ANCHOR-FOXTROT-62018. Reply with: FOXTROT-STORED.",
    )
    chat_panel = task_page.get_chat_panel()
    assert_last_message_contains(chat_panel, "FOXTROT-STORED")

    # Start a long essay
    send_no_wait(
        chat_panel,
        "Write a 3000-word essay about space travel. Start with SPACE-ESSAY:",
    )
    wait_for_streaming_text(chat_panel, "SPACE-ESSAY")

    # Interrupt and send a recall question
    interrupt_and_send(
        chat_panel,
        task_page._page,
        "Stop. What is the code I asked you to remember? Reply starting with: RECALL-FOXTROT:",
    )

    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=RESPONSE_TIMEOUT_MS)
    assert_any_message_contains(chat_panel, "ANCHOR-FOXTROT-62018")


# ---------------------------------------------------------------------------
# Interrupt during background process
# ---------------------------------------------------------------------------


@real_claude
@pytest.mark.timeout(300)
def test_interrupt_during_background_process(sculptor_instance_: SculptorInstance) -> None:
    """Verify interrupt works when agent has launched a background task.

    NOTE: Whether Claude actually runs a background task vs a regular one is
    up to Claude. The key assertion is that interrupt + recovery works.
    """
    task_page = create_workspace_and_send(
        sculptor_instance_,
        "I need you to help me set up a long-running dev server. First, use the Bash tool with run_in_background=true to run: sleep 120. Then while that's running, write a detailed README.md for a new Python web project. Include sections for installation, usage, configuration, API reference, and contributing guidelines. Start the file with: # BG-PROJECT-README-61037",
        wait_for_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Wait for some output (either the background task indicator or README text)
    wait_for_any_assistant_text(chat_panel)

    interrupt_agent(chat_panel)
    assert_interrupted(chat_panel)

    # Verify recovery
    send_and_wait(
        chat_panel,
        "Good, the interrupt worked. Please confirm by saying the phrase BG-INTERRUPT-RECOVERED-61037 so I know you're back.",
    )
    assert_last_message_contains(chat_panel, "BG-INTERRUPT-RECOVERED-61037")


# ---------------------------------------------------------------------------
# Multiple rapid interrupts in sequence
# ---------------------------------------------------------------------------


@real_claude
@pytest.mark.timeout(300)
def test_multiple_rapid_interrupts(sculptor_instance_: SculptorInstance) -> None:
    """Verify system remains stable through burst of interrupt/resume cycles."""
    task_page = create_workspace_and_send(
        sculptor_instance_,
        "Write a 2000-word essay about mountains.",
        wait_for_finish=False,
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_any_assistant_text(chat_panel)
    interrupt_agent(chat_panel)

    send_no_wait(chat_panel, "Write a 2000-word essay about rivers.")
    wait_for_any_assistant_text(chat_panel)
    interrupt_agent(chat_panel)

    send_no_wait(chat_panel, "Write a 2000-word essay about forests.")
    wait_for_any_assistant_text(chat_panel)
    interrupt_agent(chat_panel)

    # After three rapid interrupts, the agent should still be functional
    send_and_wait(chat_panel, "Reply with exactly: TRIPLE-INTERRUPT-SURVIVED-88341")
    assert_last_message_contains(chat_panel, "TRIPLE-INTERRUPT-SURVIVED-88341")


# ---------------------------------------------------------------------------
# Interrupt during AskUserQuestion
# ---------------------------------------------------------------------------


@real_claude
@pytest.mark.timeout(300)
def test_stop_button_hidden_during_ask_user_question(sculptor_instance_: SculptorInstance) -> None:
    """Verify the stop button is hidden once AskUserQuestion is visible.

    The stop button should not be clickable while AUQ is showing — the user
    should dismiss or answer the question instead.
    """
    task_page = create_workspace_and_send(
        sculptor_instance_,
        ("Ask me a question using AskUserQuestion: 'What pet do you have?' with options ['Dog', 'Cat', 'Fish']."),
        wait_for_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    ask_panel = get_ask_user_question_panel(chat_panel._page)
    expect(ask_panel).to_be_visible(timeout=RESPONSE_TIMEOUT_MS)

    # The stop button should NOT be visible when AUQ is showing
    stop_button = chat_panel.get_stop_button()
    expect(stop_button).not_to_be_visible()
