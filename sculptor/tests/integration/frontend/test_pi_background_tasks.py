"""Background-task surface under pi (REQ-CAP-BACKGROUND-TASKS, behaviour test).

pi reports ``supports_background_tasks=True``: the pinned ``sculptor_background``
extension starts a command in the background, the launching turn does not block,
and Sculptor holds the turn open (StatusPill "Waiting") until the task reports
completion out-of-band — the same harness-agnostic surface Claude drives
(covered for Claude by ``test_status_pill_background_wait.py``). There is no
disabled-affordance to assert (the ``useTaskSupportsBackgroundTasks`` gate is
substrate only); the capability IS the working surface, so this exercises it
end-to-end under pi with the deterministic ``fake_pi:background`` directive.

``fake_pi:background`` with a ``wait_path`` holds the task open on a sentinel
file (no wall-clock): the test observes the held-open surface, sends a
mid-flight message to prove the main thread stays interactive, then releases the
sentinel and asserts the completion is reconciled into the conversation.
"""

import tempfile
import uuid
from pathlib import Path

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.fake_pi import install_fake_pi_binary
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story(
    "to run a command in the background under pi: the turn does not block, the status pill shows a background "
    + "wait, the main thread stays interactive, and the completion is reconciled into the conversation"
)
def test_pi_background_task_holds_open_stays_interactive_then_completes(
    sculptor_instance_: SculptorInstance,
) -> None:
    page = sculptor_instance_.page
    install_fake_pi_binary(sculptor_instance_.fake_bin_dir)
    release_path = Path(tempfile.gettempdir()) / f"pi_background_{uuid.uuid4().hex}"
    summary_marker = "PI-BG-DONE-71024"
    try:
        task_page = start_task_and_wait_for_ready(
            sculptor_page=page,
            workspace_name="Pi Background Task",
            model_name=None,
            agent_type="pi",
            # Launch a background task held open on the sentinel: the tool returns
            # immediately (the launching run's agent_end fires), then Sculptor holds
            # the turn open until the completion notify after release().
            prompt=(
                'fake_pi:background `{"command": "sleep 1", "label": "build", "pgid": 0, '
                + f'"summary": "{summary_marker}", "wait_path": "{release_path}"}}`'
            ),
            wait_for_agent_to_finish=False,
        )
        chat_panel = task_page.get_chat_panel()

        # Behaviour 1 — the background task is in flight: the launching run ended
        # (the agent did not block) but the turn is held open, so the StatusPill
        # shows the background-wait state, NOT thinking / streaming / calling-tools.
        pill = chat_panel.get_status_pill()
        expect(pill).to_have_attribute("data-agent-state", "waiting_for_background", timeout=15000)
        expect(chat_panel.get_status_pill_label()).to_contain_text("Waiting")

        # Behaviour 2 — the main thread stays interactive while the task runs: a
        # message typed now is accepted (queued), not refused or dropped.
        send_chat_message(chat_panel=chat_panel, message="still here while it runs")
        expect(chat_panel.get_queued_message_bar()).to_have_count(1)
    finally:
        # Release the held-open task; harmless if the turn already ended.
        release_path.touch()

    # The completion is reconciled into the conversation (the summary surfaces as
    # an assistant message) and the background-wait chrome clears.
    messages = chat_panel.get_messages()
    expect(messages.filter(has_text=summary_marker).first).to_be_visible(timeout=30000)
    expect(page.get_by_test_id(ElementIDs.STATUS_PILL)).to_have_count(0, timeout=30000)
