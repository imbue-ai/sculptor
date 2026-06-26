"""In-flight send contract: while a `POST .../messages` is outstanding, the
send button shows a spinner and is disabled, the editor goes read-only while
keeping the typed prompt, and a second send attempt is a no-op so the same
message can't be queued twice. Once the POST resolves, the editor clears and
the in-flight state lifts.

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

        # While the POST is held: the button spins and is disabled, and the
        # editor is read-only but still shows the typed prompt (not lost, not
        # cleared until the send succeeds).
        expect(send_button).to_have_attribute("data-loading", "true")
        expect(send_button).to_be_disabled()
        expect(chat_input).to_have_attribute("contenteditable", "false")
        expect(chat_input).to_have_text("second message")

        # Try to send again while the first send is still in flight. The button
        # is disabled (can't be clicked) and the keyboard path is guarded, so no
        # second POST is issued.
        chat_input.click()
        page.keyboard.press("Enter")
        page.wait_for_timeout(300)
        assert state["post_count"] == 1, f"expected a single send, saw {state['post_count']}"
    finally:
        state["release"] = True
        # Let the held request continue before tearing down the route.
        page.wait_for_timeout(100)
        page.unroute(_SEND_MESSAGE_PATTERN, hold_send)

    # Once the send resolves, the in-flight state lifts: the editor clears and
    # becomes editable again, and the spinner is gone.
    expect(chat_input).to_have_text("")
    expect(chat_input).to_have_attribute("contenteditable", "true")
    expect(send_button).not_to_have_attribute("data-loading", "true")
    # Exactly one message ever hit the network.
    assert state["post_count"] == 1, f"expected a single send, saw {state['post_count']}"
