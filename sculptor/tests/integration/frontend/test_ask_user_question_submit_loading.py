"""In-flight answer-submit contract: while a `POST .../answer_question` is
outstanding, the Submit button disables immediately, the spinner appears once
the submit is slow enough to outlast its start delay, and a second submit
attempt is a no-op so the same answers can't be submitted twice. Once the POST
resolves, the panel dismisses.

Regression: the Submit button had no in-flight feedback or re-entrancy guard, so
on a slow backend the user got no feedback and a re-submit (click or Enter) sent
the answers a second time.
"""

import re

from playwright.sync_api import Route
from playwright.sync_api import expect

from sculptor.testing.elements.ask_user_question import get_ask_user_question_panel
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# `$` anchor keeps any other agent sub-route from being intercepted.
_ANSWER_PATTERN = re.compile(r"/api/v1/workspaces/[^/]+/agents/[^/]+/answer_question$")

_ASK_PROMPT = """\
fake_claude:ask_user_question `{
  "questions": [
    {
      "question": "What programming language do you prefer?",
      "header": "Language",
      "options": [
        {"label": "Python", "description": "A versatile language"},
        {"label": "JavaScript", "description": "For web development"},
        {"label": "Rust", "description": "For systems programming"}
      ],
      "multiSelect": false
    }
  ]
}`"""


@user_story("to see a submitting state (and not double-submit) when the backend is slow to accept my answer")
def test_in_flight_answer_submit_locks_button_and_blocks_double_submit(
    sculptor_instance_: SculptorInstance,
) -> None:
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=_ASK_PROMPT,
        wait_for_agent_to_finish=False,
    )
    ask_panel = get_ask_user_question_panel(page)
    expect(ask_panel).to_be_visible(timeout=30_000)

    submit_button = ask_panel.get_submit_button()
    expect(submit_button).to_be_disabled()
    ask_panel.get_options().first.click()
    expect(submit_button).to_be_enabled()

    # Hold the answer POST in flight until released, counting POSTs so a double
    # submit is observable.
    state = {"release": False, "post_count": 0}

    def hold_answer(route: Route) -> None:
        if route.request.method == "POST":
            state["post_count"] += 1
            while not state["release"]:
                page.wait_for_timeout(50)
        route.continue_()

    page.route(_ANSWER_PATTERN, hold_answer)

    try:
        submit_button.click()

        # The button locks immediately and the panel stays up while the submit
        # is in flight.
        expect(submit_button).to_be_disabled()
        expect(ask_panel).to_be_visible()
        # The spinner is latched behind a start delay so quick submits never
        # flash it. This submit is held, so it appears once the delay elapses.
        expect(submit_button).to_have_attribute("data-loading", "true")

        # Try to submit again while the first submit is in flight. The button is
        # disabled (can't be clicked) and the Enter path is guarded; the count is
        # checked below once the panel-dismissal barrier guarantees the network
        # has settled.
        page.keyboard.press("Enter")

        # Release and wait on a positive condition rather than a fixed sleep: the
        # panel dismisses only after the single answer's success response clears
        # the pending question over the WebSocket. A stray second request is
        # dispatched synchronously at the Enter above, so by the time the first
        # POST has round-tripped it would already have hit the route counter.
        state["release"] = True
        expect(ask_panel).not_to_be_visible(timeout=30_000)
        assert state["post_count"] == 1, f"expected a single answer submit, saw {state['post_count']}"
    finally:
        # Release in case an assertion above failed while the POST was still held,
        # then tear down the route.
        state["release"] = True
        page.unroute(_ANSWER_PATTERN, hold_answer)
