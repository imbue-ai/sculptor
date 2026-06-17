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


@user_story("to see a background task that fails surface its failure under pi, rather than be silently dropped")
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


@user_story("to confirm a background task under pi survives the user stopping a later turn")
def test_pi_background_task_survives_stop(sculptor_instance_: SculptorInstance) -> None:
    """A backgrounded task is independent of the turn that launched it: stopping a LATER
    turn must not kill it — once released, its completion still surfaces."""
    page = sculptor_instance_.page
    install_fake_pi_binary(sculptor_instance_.fake_bin_dir)
    task_release = Path(tempfile.gettempdir()) / f"pi_bg_survive_task_{uuid.uuid4().hex}"
    busy_release = Path(tempfile.gettempdir()) / f"pi_bg_survive_busy_{uuid.uuid4().hex}"
    summary_marker = "PI-BG-SURVIVE-90613"
    try:
        task_page = start_task_and_wait_for_ready(
            sculptor_page=page,
            workspace_name="Pi Background Survives Stop",
            model_name=None,
            agent_type="pi",
            prompt=(
                'fake_pi:background `{"command": "sleep 1", "label": "build", "pgid": 0, '
                + f'"summary": "{summary_marker}", "wait_path": "{task_release}"}}`'
            ),
            wait_for_agent_to_finish=True,
        )
        chat_panel = task_page.get_chat_panel()

        # Start a second, cancellable turn (it blocks on a sentinel) and Stop it. The
        # background task — held on its OWN sentinel — must survive that interrupt.
        send_chat_message(chat_panel=chat_panel, message=f'fake_pi:wait_for_file `{{"path": "{busy_release}"}}`')
        expect(chat_panel.get_thinking_indicator()).to_be_visible()
        stop_button = chat_panel.get_stop_button()
        expect(stop_button).to_be_visible()
        stop_button.click()
        expect(chat_panel.get_thinking_indicator()).not_to_be_visible()

        # Release the background task: its completion still surfaces, proving the Stop
        # did not kill it.
        task_release.touch()
        expect(chat_panel.get_messages().filter(has_text=summary_marker).first).to_be_visible(timeout=30000)
    finally:
        task_release.touch()
        busy_release.touch()
