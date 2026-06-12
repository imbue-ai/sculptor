"""Shared helpers for real Claude integration tests.

These helpers wrap common patterns for sending prompts, waiting for responses,
interrupting the agent, and asserting on chat content when using the real Claude CLI.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import type_into_tiptap
from sculptor.testing.elements.chat_panel import PlaywrightChatPanelElement
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance

# Pytest marker for real Claude tests. Use as @real_claude on every test function.
real_claude = pytest.mark.real_claude

# Every prompt is prefixed with this to improve Claude's compliance with exact instructions.
_TEST_PREFIX = "[SCULPTOR-UI-TEST] This is an automated integration test of Sculptor's UI, not a real user request. Follow the instructions exactly as given. "

# The model to use for real Claude tests. Must match the dropdown option text exactly.
REAL_CLAUDE_MODEL = "Claude 4.6 Sonnet"

# Timeouts for real Claude (much longer than FakeClaude).
RESPONSE_TIMEOUT_MS = 120_000  # 2 minutes for a single response
STREAMING_WAIT_TIMEOUT_MS = 60_000  # 1 minute to wait for streaming text to appear
INTERRUPT_TIMEOUT_MS = 30_000  # 30 seconds for interrupt to complete


def prefixed(prompt: str) -> str:
    """Add the test prefix to a prompt."""
    return _TEST_PREFIX + prompt


def create_workspace_and_send(
    instance: SculptorInstance,
    prompt: str,
    *,
    wait_for_finish: bool = True,
) -> PlaywrightTaskPage:
    """Create a workspace with real Claude and send the first prompt.

    Returns the task page. If wait_for_finish is True, waits for the agent
    to finish responding before returning.
    """
    return start_task_and_wait_for_ready(
        sculptor_page=instance.page,
        prompt=prefixed(prompt),
        wait_for_agent_to_finish=wait_for_finish,
        model_name=REAL_CLAUDE_MODEL,
    )


def send_and_wait(
    chat_panel: PlaywrightChatPanelElement,
    prompt: str,
    timeout_ms: int = RESPONSE_TIMEOUT_MS,
) -> None:
    """Send a message and wait for the agent to finish responding.

    Uses the flicker-tolerant settle helper because in alpha the StatusPill
    can unmount briefly between an interrupted/finished turn and the start
    of the next one — a plain ``not_to_be_visible`` then returns the moment
    the previous turn's pill disappears, before the agent has even started
    responding to the new prompt. Callers downstream rely on the assistant
    reply being present, so wait for the indicator to stay off for a
    consistent window (settle_ms, ~3s by default).
    """
    send_chat_message(chat_panel=chat_panel, message=prefixed(prompt))
    wait_for_thinking_indicator_to_settle(chat_panel, timeout_ms=timeout_ms)


def send_no_wait(chat_panel: PlaywrightChatPanelElement, prompt: str) -> None:
    """Send a message without waiting for completion (for interrupt tests)."""
    send_chat_message(chat_panel=chat_panel, message=prefixed(prompt))


def _get_assistant_messages(chat_panel: PlaywrightChatPanelElement) -> Locator:
    """Return a locator matching only assistant messages (not user messages).

    Thin wrapper around ``chat_panel.get_assistant_messages`` kept under the
    test-helpers module name so existing imports stay stable.
    """
    return chat_panel.get_assistant_messages()


def wait_for_streaming_text(
    chat_panel: PlaywrightChatPanelElement,
    sentinel: str,
    timeout_ms: int = STREAMING_WAIT_TIMEOUT_MS,
) -> None:
    """Wait until the sentinel text appears in an assistant message, even during streaming.

    This does NOT wait for the agent to finish — it returns as soon as the
    sentinel is visible in any assistant message. Used to know when it's safe
    to interrupt.

    Important: we filter to assistant messages only. After send_no_wait, the
    last message is the user's own prompt which may contain the sentinel text.
    """
    assistant_messages = _get_assistant_messages(chat_panel)
    expect(assistant_messages.last).to_contain_text(sentinel, timeout=timeout_ms)


def wait_for_any_assistant_text(
    chat_panel: PlaywrightChatPanelElement,
    timeout_ms: int = STREAMING_WAIT_TIMEOUT_MS,
) -> None:
    """Wait until the assistant has produced at least some visible text.

    Useful for interrupt tests where we want to stop as soon as streaming begins.
    We wait for the thinking indicator to appear (agent started) and then for
    the last assistant message to have any non-empty text content.
    """
    expect(chat_panel.get_thinking_indicator()).to_be_visible(timeout=30_000)
    assistant_messages = _get_assistant_messages(chat_panel)
    expect(assistant_messages.last).not_to_have_text("", timeout=timeout_ms)


def wait_for_thinking_indicator_to_settle(
    chat_panel: PlaywrightChatPanelElement,
    *,
    timeout_ms: int = RESPONSE_TIMEOUT_MS,
    settle_ms: int = 3_000,
    poll_ms: int = 200,
    visible_grace_ms: int = 30_000,
) -> None:
    """Wait until the agent is *consistently* idle.

    Plain ``expect(thinking_indicator).not_to_be_visible()`` fires the instant
    the indicator drops out — which in alpha happens between consecutive turns
    (the StatusPill unmounts briefly when a request finalizes before the next
    one starts via, e.g., a background-task notification or ScheduleWakeup),
    and also at t=0 before the agent has even spun up. Tests that measure
    "agent is fully done" with that primitive race those gaps and either
    return at 0.0s or pass for the wrong reason.

    This helper first waits up to ``visible_grace_ms`` for the indicator to
    become visible at least once (otherwise we'd treat an unstarted agent as
    "settled"), then requires the indicator to remain not-visible for
    ``settle_ms`` of wall-clock time before returning so brief mid-turn
    flickers don't satisfy it. If the indicator never appears within the
    grace window we still treat the run as settled — the agent may have
    finished before our first poll, which is fine.
    """
    indicator = chat_panel.get_thinking_indicator()
    deadline = time.monotonic() + timeout_ms / 1000.0
    grace_deadline = time.monotonic() + visible_grace_ms / 1000.0
    saw_visible = False
    consecutive_off_since: float | None = None
    while time.monotonic() < deadline:
        # ``count()`` is a synchronous Playwright call; using it (rather than
        # ``is_visible()``) keeps the poll cheap and avoids 5-second per-check
        # auto-waits baked into the assertion API.
        visible = indicator.count() > 0
        now = time.monotonic()
        if visible:
            saw_visible = True
            consecutive_off_since = None
        else:
            if not saw_visible and now < grace_deadline:
                # Don't count "off" before the agent has even started; otherwise
                # an unstarted (or about-to-start) agent satisfies the settle
                # check before any work happens.
                consecutive_off_since = None
            else:
                if consecutive_off_since is None:
                    consecutive_off_since = now
                elif (now - consecutive_off_since) * 1000.0 >= settle_ms:
                    return
        chat_panel._page.wait_for_timeout(poll_ms)
    raise AssertionError(
        f"Thinking indicator did not stay off for {settle_ms}ms within {timeout_ms}ms (saw_visible={saw_visible})"
    )


def interrupt_agent(chat_panel: PlaywrightChatPanelElement) -> None:
    """Click the stop button and wait for the interrupt to complete.

    Alpha unmounts ``STATUS_PILL_STOP`` once the pill's ``isCancellable`` flag
    goes false (the agent transitions to ``stopping``). After the click,
    Playwright can still hold a stale locator for the brief instant the button
    is being unmounted, so we explicitly wait for the test-id to leave the DOM
    or become aria-disabled before checking the thinking indicator.
    """
    stop_button = chat_panel.get_stop_button()
    expect(stop_button).to_be_visible(timeout=10_000)
    stop_button.click()
    chat_panel._page.wait_for_function(
        """(statusStopId) => {
            const els = document.querySelectorAll(`[data-testid="${statusStopId}"]`);
            if (els.length === 0) return true;
            return Array.from(els).every((el) => el.hasAttribute('disabled') || el.getAttribute('aria-disabled') === 'true');
        }""",
        arg=ElementIDs.STATUS_PILL_STOP,
        timeout=INTERRUPT_TIMEOUT_MS,
    )
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=INTERRUPT_TIMEOUT_MS)


def interrupt_and_send(
    chat_panel: PlaywrightChatPanelElement,
    page: Page,
    new_message: str,
) -> None:
    """Type a message while agent is busy, then click 'Interrupt and send'.

    The queued message bar should appear with a send button that interrupts
    the current generation and sends the new message.
    """
    chat_input = chat_panel.get_chat_input()
    type_into_tiptap(page, chat_input, prefixed(new_message))
    # The send button should now act as "interrupt and send"
    chat_panel.get_send_button().click()
    expect(chat_input).to_have_text("")


def assert_last_message_contains(chat_panel: PlaywrightChatPanelElement, text: str) -> None:
    """Assert the last assistant message contains the given text."""
    messages = chat_panel.get_messages()
    expect(messages.last).to_contain_text(text, timeout=RESPONSE_TIMEOUT_MS)


def assert_message_contains(chat_panel: PlaywrightChatPanelElement, index: int, text: str) -> None:
    """Assert a specific message (by index) contains the given text."""
    messages = chat_panel.get_messages()
    expect(messages.nth(index)).to_contain_text(text, timeout=RESPONSE_TIMEOUT_MS)


def assert_any_message_contains(chat_panel: PlaywrightChatPanelElement, text: str) -> None:
    """Assert that at least one ASSISTANT message in the chat contains the given text.

    Restricted to assistant messages so a sentinel that appears verbatim
    inside the user's prompt (e.g. ``"reply with exactly SENTINEL-123"``)
    doesn't match the prompt before the agent has actually responded.
    Without this filter the alpha view's rendered user-message bubble can
    contain the sentinel and the locator picks it instantly, making
    downstream assertions race against an unstarted agent.
    """
    assistant_messages = _get_assistant_messages(chat_panel)
    matching = assistant_messages.filter(has_text=text)
    expect(matching.first).to_be_visible(timeout=RESPONSE_TIMEOUT_MS)


def assert_no_errors(chat_panel: PlaywrightChatPanelElement) -> None:
    """Verify no error blocks are visible in the chat."""
    expect(chat_panel.get_error_block()).to_have_count(0)


def assert_interrupted(chat_panel: PlaywrightChatPanelElement) -> None:
    """Assert the alpha 'Stopped' marker is visible on the interrupted message."""
    assistant_messages = _get_assistant_messages(chat_panel)
    expect(assistant_messages.last).to_contain_text("Stopped", timeout=10_000)


def assert_has_completed_tool_calls(chat_panel: PlaywrightChatPanelElement, min_count: int = 1) -> None:
    """Assert at least min_count tool calls are rendered AND completed.

    ``get_completed_tool_calls`` filters by ``data-tool-state='completed'`` so
    a stuck-in-``initializing`` row (the SCU-149 symptom) does not satisfy
    the assertion. Subagent pills don't expose a tool-state attribute — their
    mere presence indicates the Agent tool call rendered through the subagent
    path, which is the "completed" signal for that surface, so we union them
    in via ``.or_``.
    """
    completed = chat_panel.get_completed_tool_calls()
    subagents = chat_panel.get_by_test_id(ElementIDs.ALPHA_CHAT_SUBAGENT_PILL)
    combined = completed.or_(subagents)
    if min_count == 1:
        expect(combined.first).to_be_visible(timeout=RESPONSE_TIMEOUT_MS)
    else:
        # `to_have_count` auto-retries; `.count()` arithmetic would race against
        # in-flight streaming.
        expect(combined).to_have_count(min_count, timeout=RESPONSE_TIMEOUT_MS)


# ---------------------------------------------------------------------------
# Transcript file helpers
# ---------------------------------------------------------------------------


def _extract_workspace_id(url: str) -> str:
    """Extract workspace ID from a Sculptor task page URL."""
    match = re.search(r"/ws/([a-zA-Z0-9_-]+)/", url)
    if not match:
        raise ValueError(f"Could not extract workspace ID from URL: {url}")
    return match.group(1)


def get_transcript_path(
    instance: SculptorInstance,
    task_page: PlaywrightTaskPage,
) -> Path:
    """Get the Claude session transcript file path via the diagnostics API.

    Calls the backend diagnostics endpoint to retrieve the session JSONL path.
    Raises AssertionError if the transcript file doesn't exist.
    """
    base_url = instance.base_url.rstrip("/")
    workspace_id = _extract_workspace_id(task_page._page.url)
    agent_id = task_page.get_task_id()

    response = instance.page.request.get(f"{base_url}/api/v1/workspaces/{workspace_id}/agents/{agent_id}/diagnostics")
    assert response.ok, f"Diagnostics API returned {response.status}: {response.text()}"
    diagnostics = response.json()

    # API response uses camelCase (FastAPI SerializableModel aliases)
    transcript_file_path = diagnostics.get("transcriptFilePath")
    assert transcript_file_path, f"No transcript file path in diagnostics: {diagnostics}"

    path = Path(transcript_file_path)
    assert path.exists(), f"Transcript file does not exist: {path}"
    return path


def read_transcript(transcript_path: Path) -> list[dict[str, Any]]:
    """Read and parse a Claude session JSONL transcript file.

    Returns a list of parsed JSON objects, one per line. Malformed lines
    are skipped (they can occur if the CLI was interrupted mid-write).
    """
    messages: list[dict[str, Any]] = []
    for line in transcript_path.read_text().strip().splitlines():
        try:
            messages.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return messages


def get_transcript_messages(
    transcript: list[dict[str, Any]],
    role: str | None = None,
) -> list[dict[str, Any]]:
    """Filter transcript entries to conversation messages (user/assistant).

    Args:
        transcript: Parsed transcript from read_transcript().
        role: If provided, filter to only this role ("user" or "assistant").
    """
    result = []
    for entry in transcript:
        entry_type = entry.get("type")
        if entry_type not in ("user", "assistant"):
            continue
        if role and entry_type != role:
            continue
        result.append(entry)
    return result


def get_message_text(entry: dict[str, Any]) -> str:
    """Extract the full text content from a transcript message entry.

    Handles the Claude message format where content is a list of blocks,
    each with a "type" and either "text" (for text blocks) or other fields.
    """
    message = entry.get("message", {})
    content = message.get("content", [])
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return " ".join(parts)


def assert_transcript_contains(
    transcript: list[dict[str, Any]],
    text: str,
    role: str | None = None,
) -> None:
    """Assert that at least one transcript message contains the given text.

    Args:
        transcript: Parsed transcript from read_transcript().
        text: Text to search for in message content.
        role: If provided, only search messages with this role.
    """
    messages = get_transcript_messages(transcript, role=role)
    for msg in messages:
        if text in get_message_text(msg):
            return
    all_texts = [get_message_text(m)[:200] for m in messages]
    role_desc = f" (role={role})" if role else ""
    raise AssertionError(
        f"Text '{text}' not found in any transcript message{role_desc}.\nMessages ({len(messages)}): {all_texts}"
    )


def assert_transcript_turn_count(
    transcript: list[dict[str, Any]],
    role: str,
    min_count: int,
) -> None:
    """Assert that the transcript has at least min_count messages of the given role."""
    messages = get_transcript_messages(transcript, role=role)
    assert len(messages) >= min_count, (
        f"Expected at least {min_count} '{role}' messages in transcript, got {len(messages)}"
    )


def get_transcript_background_tasks(
    transcript: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Extract background task started/notification entries from the transcript.

    Returns (started, notifications) — useful for diagnosing whether background
    task completion events were properly emitted by the CLI.
    """
    started = []
    notifications = []
    for entry in transcript:
        if entry.get("type") != "system":
            continue
        subtype = entry.get("subtype")
        if subtype == "task_started":
            started.append(entry)
        elif subtype == "task_notification":
            notifications.append(entry)
    return started, notifications
