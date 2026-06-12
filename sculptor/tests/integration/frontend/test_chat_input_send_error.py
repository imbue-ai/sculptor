"""Send-error contract: on a failed `POST .../messages`, the send button
exposes `data-last-send-error`, a toast surfaces the failure, and the
editor keeps the typed prompt.
"""

import re

from playwright.sync_api import Route
from playwright.sync_api import expect

from sculptor.testing.elements.base import type_into_tiptap
from sculptor.testing.elements.toast import PlaywrightToastElement
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to see an error toast (and not lose my typed prompt) when sending a message fails")
def test_send_error_surfaces_attribute_and_toast_without_clearing_editor(
    sculptor_instance_: SculptorInstance,
) -> None:
    page = sculptor_instance_.page

    # Set the workspace + agent up first; only fail subsequent sends.
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="hello",
    )
    chat_panel = task_page.get_chat_panel()

    # `$` anchor keeps DELETE .../messages/{id} from being intercepted.
    send_message_pattern = re.compile(r"/api/v1/workspaces/[^/]+/agents/[^/]+/messages$")

    def fail_send(route: Route) -> None:
        if route.request.method == "POST":
            route.fulfill(status=500, body='{"detail": "Internal Server Error"}')
        else:
            route.continue_()

    page.route(send_message_pattern, fail_send)

    try:
        chat_input = chat_panel.get_chat_input()
        type_into_tiptap(page, chat_input, "this send will fail")
        send_button = chat_panel.get_send_button()
        expect(send_button).to_be_enabled()
        send_button.click()

        expect(send_button).to_have_attribute("data-last-send-error", re.compile(r".+"))

        toast_element = PlaywrightToastElement(page)
        toast = toast_element.filter_by_text("Failed to send message")
        expect(toast).to_be_visible()

        expect(chat_input).to_have_text("this send will fail")
    finally:
        page.unroute(send_message_pattern, fail_send)
