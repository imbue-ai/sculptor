"""Shared helpers for real pi integration tests.

Real pi tests run a real ``pi --mode rpc`` subprocess driven by a real
upstream model. Helpers keep the per-test surface small.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from collections.abc import Sequence

import psutil
import pytest
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.chat_panel import PlaywrightChatPanelElement
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance

# Pytest marker for real pi tests. Apply as ``@real_pi`` on every test.
real_pi = pytest.mark.real_pi

# Pi has no Sculptor-registered LLMModel entry; the chat panel's model picker
# is skipped (model_name=None). Pi reads its upstream-model choice from
# ``~/.pi/agent/models.json`` outside Sculptor.

# Single-turn responses against real pi can take a while (cold-start + model
# latency). Default to a roomy timeout so the suite isn't fighting noise.
RESPONSE_TIMEOUT_MS = 180_000
# Waiting for streaming text to first appear, and for an interrupt to settle.
STREAMING_WAIT_TIMEOUT_MS = 60_000
INTERRUPT_TIMEOUT_MS = 30_000

# Prefix every prompt so real pi recognises this as an automated test. Reads as
# a user instruction without conflicting with any pi system-prompt directive.
_TEST_PREFIX = "[SCULPTOR-UI-TEST] This is an automated integration test of Sculptor's UI, not a real user request. Follow the instructions exactly as given. "


def prefixed(prompt: str) -> str:
    return _TEST_PREFIX + prompt


def send_no_wait(chat_panel: PlaywrightChatPanelElement, prompt: str) -> None:
    """Send a prompt without waiting for completion (for interrupt tests)."""
    send_chat_message(chat_panel=chat_panel, message=prefixed(prompt))


def wait_for_streaming_text(
    chat_panel: PlaywrightChatPanelElement,
    sentinel: str,
    timeout_ms: int = STREAMING_WAIT_TIMEOUT_MS,
) -> None:
    """Wait until ``sentinel`` appears in an assistant message (even mid-stream).

    Filters to assistant messages so the user's own prompt (which may quote the
    sentinel) doesn't match before the agent has actually started streaming.
    """
    expect(chat_panel.get_assistant_messages().last).to_contain_text(sentinel, timeout=timeout_ms)


def interrupt_agent(chat_panel: PlaywrightChatPanelElement) -> None:
    """Click Stop and wait for the interrupt to complete.

    The Stop button unmounts (or goes aria-disabled) once the pill stops being
    cancellable, so wait for that before asserting the thinking indicator is
    gone — mirrors the real_claude helper.
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


def assert_interrupted(chat_panel: PlaywrightChatPanelElement) -> None:
    """Assert the 'Stopped' marker is visible on the interrupted assistant message."""
    expect(chat_panel.get_assistant_messages().last).to_contain_text("Stopped", timeout=INTERRUPT_TIMEOUT_MS)


def assert_last_assistant_message_contains(chat_panel: PlaywrightChatPanelElement, text: str) -> None:
    """Assert the last ASSISTANT message contains ``text`` (auto-waits for the reply)."""
    expect(chat_panel.get_assistant_messages().last).to_contain_text(text, timeout=RESPONSE_TIMEOUT_MS)


def assert_no_errors(chat_panel: PlaywrightChatPanelElement) -> None:
    expect(chat_panel.get_error_block()).to_have_count(0)


def create_pi_workspace_and_send(
    sculptor_instance_: SculptorInstance,
    prompt: str,
    *,
    workspace_name: str = "Real Pi",
    wait_for_finish: bool = True,
) -> PlaywrightTaskPage:
    """Create a real-pi workspace and send the first prompt.

    With ``wait_for_finish`` (the default) waits for the turn to complete before
    returning. Pass ``wait_for_finish=False`` for turns that block mid-way — e.g.
    an ask-user-question or plan-approval dialog the test must answer. Pi's tool
    loop runs inside the pi subprocess; Sculptor's file-watching layer reflects
    workspace mutations into the diff sidebar.
    """
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        workspace_name=workspace_name,
        prompt=prefixed(prompt),
        model_name=None,
        agent_type="pi",
        wait_for_agent_to_finish=wait_for_finish,
    )
    if wait_for_finish:
        wait_for_completed_message_count(
            chat_panel=task_page.get_chat_panel(),
            expected_message_count=2,
            timeout=RESPONSE_TIMEOUT_MS,
        )
    return task_page


def count_processes_matching(predicate: Callable[[Sequence[str]], bool]) -> int:
    """Count live processes whose argv satisfies ``predicate``.

    Backs the no-orphan assertions: see a spawned child appear and confirm it is
    gone (killed, not orphaned). Reads ``cmdline`` defensively — a process can
    exit between iteration and inspection.
    """
    count = 0
    for proc in psutil.process_iter(["cmdline"]):
        try:
            cmdline = proc.info["cmdline"] or []
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if predicate(cmdline):
            count += 1
    return count


def wait_for_process_count(
    predicate: Callable[[Sequence[str]], bool], target: int, *, at_least: bool, timeout_s: float
) -> int:
    """Poll ``count_processes_matching`` until it reaches ``target`` (or timeout)."""
    deadline = time.monotonic() + timeout_s
    last = count_processes_matching(predicate)
    while time.monotonic() < deadline:
        last = count_processes_matching(predicate)
        if (at_least and last >= target) or (not at_least and last <= target):
            return last
        time.sleep(0.5)
    return last


def kill_processes_matching(predicate: Callable[[Sequence[str]], bool]) -> None:
    """Best-effort SIGTERM of live processes whose argv satisfies ``predicate``.

    Test cleanup for a deliberately-orphaned child (e.g. a test that proves Stop
    does NOT kill a background task leaves it running). Defensive — a process can
    exit, or be inaccessible, between iteration and signalling.
    """
    for proc in psutil.process_iter(["cmdline"]):
        try:
            if predicate(proc.info["cmdline"] or []):
                proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
