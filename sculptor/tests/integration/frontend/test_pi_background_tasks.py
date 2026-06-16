"""Background-task surface under pi (REQ-CAP-BACKGROUND-TASKS, behaviour test).

pi reports ``supports_background_tasks=True``: the pinned ``sculptor_background``
extension starts a command in the background and the launching turn YIELDS
immediately — the user keeps chatting while the task runs, and the task's
completion is surfaced out-of-band (the harness-agnostic ``BackgroundTask*``
contracts). There is no disabled-affordance to assert (the
``useTaskSupportsBackgroundTasks`` gate is substrate only); the capability IS the
working surface, so this exercises it end-to-end under pi with the deterministic
``fake_pi:background`` directive.

``fake_pi:background`` with a ``wait_path`` holds the task's completion on a
sentinel file (no wall-clock), emitting it out-of-band on a daemon thread so fake
pi stays responsive. The test asserts: the launch turn ends (the user is not
blocked), a message sent WHILE the task runs gets a reply (no Stop), and once the
sentinel is released the completion is reconciled into the conversation live.
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
    "to run a command in the background under pi: the launching turn yields immediately, the main thread stays "
    + "interactive while the task runs, and the completion is surfaced into the conversation when it finishes"
)
def test_pi_background_task_yields_stays_interactive_then_completes(
    sculptor_instance_: SculptorInstance,
) -> None:
    page = sculptor_instance_.page
    install_fake_pi_binary(sculptor_instance_.fake_bin_dir)
    release_path = Path(tempfile.gettempdir()) / f"pi_background_{uuid.uuid4().hex}"
    summary_marker = "PI-BG-DONE-71024"
    reply_marker = "PI-INTERACTIVE-REPLY-55012"
    try:
        task_page = start_task_and_wait_for_ready(
            sculptor_page=page,
            workspace_name="Pi Background Task",
            model_name=None,
            agent_type="pi",
            # Launch a background task whose completion is held on the sentinel: the
            # tool returns immediately and the launching run's agent_end fires, so
            # the turn ENDS (yield-early) — the user is not blocked.
            prompt=(
                'fake_pi:background `{"command": "sleep 1", "label": "build", "pgid": 0, '
                + f'"summary": "{summary_marker}", "wait_path": "{release_path}"}}`'
            ),
            wait_for_agent_to_finish=True,
        )
        chat_panel = task_page.get_chat_panel()

        # Behaviour 1 — yield-early: reaching here means the launching turn FINISHED
        # (start_task_and_wait_for_ready waited for it; under a held-open model it
        # would have hung), so the StatusPill is gone and the input is free.
        expect(page.get_by_test_id(ElementIDs.STATUS_PILL)).to_have_count(0, timeout=15000)

        # Behaviour 2 — the main thread stays interactive WHILE the task runs (the
        # sentinel is not released yet): a message sent now is answered, with no
        # Stop required and without disturbing the running task.
        send_chat_message(chat_panel=chat_panel, message=f'fake_pi:emit_text `{{"text": "{reply_marker}"}}`')
        expect(chat_panel.get_messages().filter(has_text=reply_marker).first).to_be_visible(timeout=30000)
    finally:
        # Let the background task complete; harmless if the test already failed.
        release_path.touch()

    # The completion is surfaced out-of-band, live: the summary appears in the
    # conversation as its own assistant message.
    expect(chat_panel.get_messages().filter(has_text=summary_marker).first).to_be_visible(timeout=30000)


@user_story(
    "to see a background task that fails surface its failure under pi, rather than be silently dropped"
)
def test_pi_background_task_failure_surfaces(sculptor_instance_: SculptorInstance) -> None:
    """A background command that exits non-zero surfaces its failure out-of-band: the
    completion is reconciled into the conversation as a FAILED task (the "failed" header
    plus the command's output), not silently dropped."""
    page = sculptor_instance_.page
    install_fake_pi_binary(sculptor_instance_.fake_bin_dir)
    release_path = Path(tempfile.gettempdir()) / f"pi_background_fail_{uuid.uuid4().hex}"
    summary_marker = "PI-BG-FAIL-80517"
    try:
        task_page = start_task_and_wait_for_ready(
            sculptor_page=page,
            workspace_name="Pi Background Task Failure",
            model_name=None,
            agent_type="pi",
            # status="failed" + a non-zero exit code: the launch still yields
            # immediately; the FAILED completion is surfaced out-of-band when released.
            prompt=(
                'fake_pi:background `{"command": "exit 1", "label": "build", "pgid": 0, '
                + f'"status": "failed", "exit_code": 1, "summary": "{summary_marker}", "wait_path": "{release_path}"}}`'
            ),
            wait_for_agent_to_finish=True,
        )
        chat_panel = task_page.get_chat_panel()
    finally:
        # Release the held completion; harmless if the test already failed.
        release_path.touch()

    # The failure is surfaced live as its own assistant message: a "failed" header
    # (exit code 1) together with the command's output summary.
    expect(chat_panel.get_messages().filter(has_text=summary_marker).first).to_be_visible(timeout=30000)
    expect(chat_panel.get_messages().filter(has_text="failed").first).to_be_visible(timeout=30000)
