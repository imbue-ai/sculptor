"""Perf scenario: sending a chat message.

Captures the click → optimistic UI → thinking-state transition with
three checkpoints so we can see *where* a regression lands (input
handling, the backend POST, optimistic bubble render, or agent status
flip).

Parametrized across blend × temperature; see test_workspace_switch for
the pattern. The blend produces the chat state the measurement runs
on; the temperature decides whether we reload the SPA between blend
and measurement.
"""

from collections.abc import Callable

import pytest
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.base import type_into_tiptap
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.perf.collector import MeasurementRecorder
from sculptor.testing.playwright_utils import full_spa_reload
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# ---- Blends ---------------------------------------------------------------
# Each blend returns the PlaywrightTaskPage the measurement should send
# from. The chat must be in a stable state (no agent activity in flight)
# by the time the blend returns.


def blend_default(page: Page) -> PlaywrightTaskPage:
    """One workspace with a single completed warmup turn (2 messages)."""
    task_page = start_task_and_wait_for_ready(page, prompt="warmup", workspace_name="Perf Send")
    wait_for_completed_message_count(chat_panel=task_page.get_chat_panel(), expected_message_count=2)
    return task_page


# ---------------------------------------------------------------------------


@pytest.mark.parametrize("temperature", ["warm", "cold"])
@pytest.mark.parametrize(
    "blend",
    [
        pytest.param(blend_default, id="default"),
    ],
)
@user_story("perf: sending a message should not over-fetch or over-render")
def test_send_message(
    sculptor_instance_: SculptorInstance,
    perf_recorder: MeasurementRecorder,
    blend: Callable[[Page], PlaywrightTaskPage],
    temperature: str,
    request: pytest.FixtureRequest,
) -> None:
    page = sculptor_instance_.page
    task_page = blend(page)
    chat_panel = task_page.get_chat_panel()
    pre_send_message_count = chat_panel.get_messages().count()

    if temperature == "cold":
        # Reload back into the same task URL so the SPA boots into a chat
        # with the blend's state — the only difference from "warm" is that
        # the frontend's in-memory caches are empty.
        current_hash = page.url.split("#", 1)[1] if "#" in page.url else "/"
        full_spa_reload(page, target_hash=f"#{current_hash}")
        perf_recorder.assert_hook_wired()
        task_page = PlaywrightTaskPage(page=page)
        chat_panel = task_page.get_chat_panel()
        expect(chat_panel.get_messages()).to_have_count(pre_send_message_count)

    expected_after_send = pre_send_message_count + 1
    chat_input = chat_panel.get_chat_input()
    send_button = chat_panel.get_send_button()
    messages = chat_panel.get_messages()
    thinking = chat_panel.get_thinking_indicator()

    type_into_tiptap(page, chat_input, "measured message")
    expect(send_button).to_be_enabled()

    # "agent_acknowledged" accepts either signal: thinking indicator visible
    # OR the new assistant message already attached. Fake Claude's response
    # to short prompts can land so fast that the thinking state flashes
    # below Playwright's poll interval, so the disjunction prevents flakes
    # without losing the timing for slower (real) responses.
    new_assistant_message = messages.nth(expected_after_send)
    agent_acknowledged = thinking.or_(new_assistant_message)

    variant = request.node.callspec.id
    with perf_recorder.window(scenario="send_message", variant=variant) as w:
        send_button.click()
        w.checkpoint("input_cleared", wait_for=lambda: expect(chat_input).to_have_text(""))
        w.checkpoint(
            "user_bubble_attached",
            wait_for=lambda: expect(messages).to_have_count(expected_after_send),
        )
        w.checkpoint("agent_acknowledged", wait_for=lambda: expect(agent_acknowledged).to_be_visible())
