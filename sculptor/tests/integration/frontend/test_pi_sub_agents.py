"""Sub-agent surface under pi, async / yield-early (REQ-CAP-SUB-AGENTS, behaviour).

pi reports ``supports_sub_agents=True``: the pinned ``sculptor_subagent`` extension
delegates work to child agents and the launching turn YIELDS immediately — the
user keeps chatting while the children run — and each child's activity is surfaced
out-of-band as the nested ``AlphaSubagentPill`` when it completes.

These exercise the async sub-agent surface end-to-end under pi with the
deterministic ``fake_pi:subagent`` directive (which scripts the launch + an
out-of-band completion ``notify``, optionally held on a ``wait_path`` sentinel so
there is no wall-clock dependency):

- golden: the launch yields, the main thread stays interactive while the children
  run, and the nested pill surfaces when the completion is released;
- a failed child surfaces as the pill (with a "failed" completion), not dropped;
- a running sub-agent SURVIVES the user stopping a later turn (it is independent of
  the turn that launched it). No-orphan ON SHUTDOWN is covered by the unit tests.
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

# One scripted child that finishes cleanly with a bit of text.
_DONE_CHILD = (
    '{"childId": "c0", "label": "scout", "task": "find files", "status": "done", '
    + '"events": [{"seq": 0, "kind": "text", "text": "Found 10 files."}]}'
)


@user_story(
    "to delegate to a sub-agent under pi: the launching turn yields immediately, the main thread stays interactive "
    + "while the sub-agent runs, and its activity is surfaced as the nested pill when it finishes"
)
def test_pi_subagent_yields_stays_interactive_then_completes(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    install_fake_pi_binary(sculptor_instance_.fake_bin_dir)
    release_path = Path(tempfile.gettempdir()) / f"pi_subagent_{uuid.uuid4().hex}"
    reply_marker = "PI-SA-REPLY-55013"
    try:
        task_page = start_task_and_wait_for_ready(
            sculptor_page=page,
            workspace_name="Pi Sub-Agent",
            model_name=None,
            agent_type="pi",
            # The sub-agent launch returns immediately; its completion is held on the
            # sentinel and emitted out-of-band, so the launching run's agent_end fires
            # and the turn ENDS (yield-early) — the user is not blocked.
            prompt=f'fake_pi:subagent `{{"children": [{_DONE_CHILD}], "wait_path": "{release_path}"}}`',
            wait_for_agent_to_finish=True,
        )
        chat_panel = task_page.get_chat_panel()

        # Behaviour 1 — yield-early: reaching here means the launching turn FINISHED
        # (a held-open model would have hung), so the StatusPill is gone.
        expect(page.get_by_test_id(ElementIDs.STATUS_PILL)).to_have_count(0, timeout=15000)

        # Behaviour 2 — interactive WHILE the sub-agent runs (sentinel not released): a
        # message sent now is answered, with no Stop and without disturbing the children.
        send_chat_message(chat_panel=chat_panel, message=f'fake_pi:emit_text `{{"text": "{reply_marker}"}}`')
        expect(chat_panel.get_messages().filter(has_text=reply_marker).first).to_be_visible(timeout=30000)
    finally:
        # Let the sub-agent complete; harmless if the test already failed.
        release_path.touch()

    # The completion is surfaced out-of-band, live: the child's activity renders as
    # the nested sub-agent pill.
    expect(page.get_by_test_id(ElementIDs.ALPHA_CHAT_SUBAGENT_PILL).first).to_be_visible(timeout=30000)


@user_story("to see a sub-agent whose child fails surface as the sub-agent pill under pi, not be silently dropped")
def test_pi_subagent_failure_surfaces(sculptor_instance_: SculptorInstance) -> None:
    """A sub-agent that finishes failed (a child errored) still renders as the
    sub-agent pill and surfaces a "failed" completion, rather than vanishing."""
    page = sculptor_instance_.page
    install_fake_pi_binary(sculptor_instance_.fake_bin_dir)
    release_path = Path(tempfile.gettempdir()) / f"pi_subagent_fail_{uuid.uuid4().hex}"
    error_child = '{"childId": "c0", "label": "scout", "task": "find files", "status": "error", "events": []}'
    try:
        task_page = start_task_and_wait_for_ready(
            sculptor_page=page,
            workspace_name="Pi Sub-Agent Failure",
            model_name=None,
            agent_type="pi",
            prompt=f'fake_pi:subagent `{{"status": "failed", "children": [{error_child}], "wait_path": "{release_path}"}}`',
            wait_for_agent_to_finish=True,
        )
        chat_panel = task_page.get_chat_panel()
    finally:
        release_path.touch()

    # The failed sub-agent still renders as the nested pill, and the failure is
    # visible (the failed child + completion summary carry "failed").
    expect(page.get_by_test_id(ElementIDs.ALPHA_CHAT_SUBAGENT_PILL).first).to_be_visible(timeout=30000)
    expect(chat_panel.get_messages().filter(has_text="failed").first).to_be_visible(timeout=30000)


@user_story("to confirm a sub-agent under pi survives the user stopping a later turn")
def test_pi_subagent_survives_stop(sculptor_instance_: SculptorInstance) -> None:
    """A running sub-agent is independent of the turn that launched it: stopping a
    LATER turn must not kill it — once released, its completion still surfaces."""
    page = sculptor_instance_.page
    install_fake_pi_binary(sculptor_instance_.fake_bin_dir)
    task_release = Path(tempfile.gettempdir()) / f"pi_sa_survive_task_{uuid.uuid4().hex}"
    busy_release = Path(tempfile.gettempdir()) / f"pi_sa_survive_busy_{uuid.uuid4().hex}"
    try:
        task_page = start_task_and_wait_for_ready(
            sculptor_page=page,
            workspace_name="Pi Sub-Agent Survives Stop",
            model_name=None,
            agent_type="pi",
            prompt=f'fake_pi:subagent `{{"children": [{_DONE_CHILD}], "wait_path": "{task_release}"}}`',
            wait_for_agent_to_finish=True,
        )
        chat_panel = task_page.get_chat_panel()

        # Start a second, cancellable turn (it blocks on a sentinel) and Stop it. The
        # sub-agent — held on its own sentinel — must survive that interrupt.
        send_chat_message(chat_panel=chat_panel, message=f'fake_pi:wait_for_file `{{"path": "{busy_release}"}}`')
        expect(chat_panel.get_thinking_indicator()).to_be_visible()
        stop_button = chat_panel.get_stop_button()
        expect(stop_button).to_be_visible()
        stop_button.click()
        expect(chat_panel.get_thinking_indicator()).not_to_be_visible()

        # Release the sub-agent: its nested pill still surfaces, proving the Stop did
        # not kill it.
        task_release.touch()
        expect(page.get_by_test_id(ElementIDs.ALPHA_CHAT_SUBAGENT_PILL).first).to_be_visible(timeout=30000)
    finally:
        task_release.touch()
        busy_release.touch()


@user_story("to see the calling agent auto-resume when its sub-agent finishes under pi")
def test_pi_subagent_completion_auto_resumes_the_agent(sculptor_instance_: SculptorInstance) -> None:
    """When a sub-agent finishes, Sculptor wakes the calling agent with its own prompt
    (SCU-1776: pi never self-starts a run) and the reaction surfaces as a new turn
    after the launch turn yielded — FakePi answers the wake prompt with its default
    text, which is the reaction turn this asserts on."""
    page = sculptor_instance_.page
    install_fake_pi_binary(sculptor_instance_.fake_bin_dir)
    release_path = Path(tempfile.gettempdir()) / f"pi_sa_autoresume_{uuid.uuid4().hex}"
    try:
        task_page = start_task_and_wait_for_ready(
            sculptor_page=page,
            workspace_name="Pi Sub-Agent Auto-Resume",
            model_name=None,
            agent_type="pi",
            prompt=f'fake_pi:subagent `{{"children": [{_DONE_CHILD}], "wait_path": "{release_path}"}}`',
            wait_for_agent_to_finish=True,
        )
        chat_panel = task_page.get_chat_panel()
    finally:
        release_path.touch()

    # The sub-agent completes; Sculptor sends the wake prompt and the reaction turn
    # surfaces (FakePi's default reply to the wake).
    expect(chat_panel.get_assistant_messages().filter(has_text="[FakePi] Task completed.").first).to_be_visible(
        timeout=30000
    )
    expect(page.get_by_test_id(ElementIDs.ALPHA_CHAT_SUBAGENT_PILL).first).to_be_visible(timeout=30000)
