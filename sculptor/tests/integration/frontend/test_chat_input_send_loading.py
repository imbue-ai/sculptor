"""In-flight send contract: while a `POST .../messages` is outstanding, the
send button disables and the editor goes read-only immediately (keeping the
typed prompt), the spinner appears once the send is slow enough to outlast its
start delay, and a second send attempt is a no-op so the same message can't be
queued twice. Once the POST resolves, the editor clears and the in-flight state
lifts.

Regression: the send was fire-and-forget with no in-flight feedback or
re-entrancy guard, so on a slow backend the user saw nothing happen and a
re-send queued the message a second time.
"""

import re

from playwright.sync_api import Route
from playwright.sync_api import expect

from sculptor.testing.elements.base import type_into_tiptap
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# `$` anchor keeps DELETE .../messages/{id} from being intercepted.
_SEND_MESSAGE_PATTERN = re.compile(r"/api/v1/workspaces/[^/]+/agents/[^/]+/messages$")


@user_story("to see a sending state (and not double-queue) when the backend is slow to accept my message")
def test_in_flight_send_shows_spinner_locks_editor_and_blocks_double_send(
    sculptor_instance_: SculptorInstance,
) -> None:
    page = sculptor_instance_.page

    # Set the workspace + agent up first; only hold subsequent sends in flight.
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="hello",
    )
    chat_panel = task_page.get_chat_panel()

    # Hold the next message POST in flight until the test releases it, and count
    # how many POSTs actually reach the network so a double-send is observable.
    state = {"release": False, "post_count": 0}

    def hold_send(route: Route) -> None:
        if route.request.method == "POST":
            state["post_count"] += 1
            while not state["release"]:
                page.wait_for_timeout(50)
        route.continue_()

    page.route(_SEND_MESSAGE_PATTERN, hold_send)

    try:
        chat_input = chat_panel.get_chat_input()
        type_into_tiptap(page, chat_input, "second message")
        send_button = chat_panel.get_send_button()
        expect(send_button).to_be_enabled()
        send_button.click()

        # The input locks immediately: the send button disables and the editor
        # goes read-only while still showing the typed prompt (not lost, not
        # cleared until the send succeeds).
        expect(send_button).to_be_disabled()
        expect(chat_input).to_have_attribute("contenteditable", "false")
        expect(chat_input).to_have_text("second message")
        # The spinner is latched behind a start delay so quick sends never flash
        # it. This send is held in flight, so it appears once the delay elapses.
        expect(send_button).to_have_attribute("data-loading", "true")

        # Try to send again while the first send is still in flight. The button
        # is disabled (can't be clicked) and the keyboard path is guarded. A
        # broken guard would dispatch a second POST here; the count is checked
        # below once the editor-clear barrier guarantees the network has settled.
        chat_input.click()
        page.keyboard.press("Enter")

        # Release the held send and wait on a positive condition rather than a
        # fixed sleep: the editor clears (and re-enables) and the spinner lifts
        # only after the single send's success response. A stray second request
        # is dispatched synchronously at the Enter above, so by the time the
        # first POST has round-tripped it would already have hit the route
        # counter — making this a reliable happens-after barrier for the assert.
        state["release"] = True
        expect(chat_input).to_have_text("")
        expect(chat_input).to_have_attribute("contenteditable", "true")
        expect(send_button).not_to_have_attribute("data-loading", "true")
        # Exactly one message ever hit the network: the re-entrancy guard held.
        assert state["post_count"] == 1, f"expected a single send, saw {state['post_count']}"
    finally:
        # Release in case an assertion above failed while the send was still held,
        # then tear down the route.
        state["release"] = True
        page.unroute(_SEND_MESSAGE_PATTERN, hold_send)
