"""Regression test: conversation launch settings must survive a Sculptor restart.

A turn that carries no model of its own — a question answer, or an
answer-continuation resume — continues the conversation with its existing
launch settings (model, fast mode, effort). Those settings live in
``ClaudeProcessManager`` memory and are seeded from replayed history when the
runner starts a task, so they must hold even on a manager constructed after a
backend restart. Without the seeding, the relaunched CLI gets fresh-manager
defaults: a fake_claude conversation relaunches the real-claude command shape
(and dies on the test binary stub), and a real conversation silently drops
the user's fast-mode and effort choices.

The scenario uses a pending ask_user_question purely as the vehicle: it is
the natural way to park a conversation so that the first turn after the
restart is model-less (the answer). The pending-question restoration
behavior itself is pinned separately in
``test_regression_pending_question_restored_on_restart.py``.

The relaunched CLI's actual arguments are observed from the UI via
fake_claude's opt-in launch-args echo (``CLAUDE_FAKE_ECHO_LAUNCH_ARGS``):
each cycle appends a chat-visible line stating the model / fast-mode /
effort / resume flags the CLI was launched with.
"""

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.ask_user_question import get_ask_user_question_panel
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

_SECONDS_MS = 1000

# Visibility gate for the post-restart page — generous because the Phase-2
# backend is restoring a previously-running task and CI can be slow.
_RESTART_VISIBILITY_TIMEOUT_MS = 60 * _SECONDS_MS

# Before tearing down the first instance, wait this long for the agent to
# actually reach the question-waiting state — the restart must interrupt a
# parked conversation, not a mid-turn one.
_INFLIGHT_OBSERVATION_TIMEOUT_MS = 30 * _SECONDS_MS

# Window for the post-restart answer's resumed turn to complete (spawn CLI
# with --resume, deliver the answer, emit the follow-up + echo).
_SETTLE_TIMEOUT_MS = 60 * _SECONDS_MS

_AUQ_PROMPT = 'fake_claude:ask_user_question `{"questions": [{"question": "Pick a color", "header": "Color", "options": [{"label": "Red", "description": "warm"}, {"label": "Blue", "description": "cool"}], "multiSelect": false}]}`'  # noqa: E501


def _open_workspace_after_restart(page: Page) -> None:
    """Click the persisted workspace's sidebar row on a fresh Sculptor instance."""
    workspace_row = get_workspace_sidebar(page).get_workspace_rows().first
    expect(workspace_row).to_be_visible(timeout=_RESTART_VISIBILITY_TIMEOUT_MS)
    workspace_row.click()


@user_story("keep my model settings when answering an agent's question after restarting Sculptor")
def test_launch_settings_preserved_for_answer_after_restart(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """A post-restart answer must relaunch the CLI with the conversation's settings.

    Drive non-default settings through the real chat controls (fast mode on,
    effort Low), park the agent on a question, restart, answer — and assert
    via the launch-args echo that the resumed turn's CLI relaunched with
    those same settings rather than fresh-manager defaults (fast mode off,
    effort xhigh).

    The question turn's own echo never lands — its cycle dies with the
    restart — so exactly one echo exists afterwards: the answer turn's.
    """
    sculptor_instance_factory_.update_environment(CLAUDE_FAKE_ECHO_LAUNCH_ARGS="1")

    with sculptor_instance_factory_.spawn_instance() as instance:
        task_page = start_task_and_wait_for_ready(instance.page)
        chat_panel = task_page.get_chat_panel()

        # Non-default launch settings, set through the real UI controls.
        chat_panel.get_fast_mode_toggle().click()
        expect(chat_panel.get_fast_mode_toggle()).to_have_attribute("data-active", "true")
        chat_panel.select_effort("Low")
        expect(chat_panel.get_effort_selector()).to_have_attribute("data-value", "low")

        send_chat_message(chat_panel, _AUQ_PROMPT)
        expect(get_ask_user_question_panel(instance.page)).to_be_visible(timeout=_INFLIGHT_OBSERVATION_TIMEOUT_MS)

    with sculptor_instance_factory_.spawn_instance() as instance:
        _open_workspace_after_restart(instance.page)

        auq_panel = get_ask_user_question_panel(instance.page)
        expect(auq_panel).to_be_visible(timeout=_RESTART_VISIBILITY_TIMEOUT_MS)
        auq_panel.select_first_option_and_submit()
        expect(auq_panel).not_to_be_visible(timeout=_SETTLE_TIMEOUT_MS)

        # The relaunched CLI must carry the conversation's settings: fast mode
        # and effort from the pre-restart chat turn, resuming the session.
        chat_panel = PlaywrightTaskPage(page=instance.page).get_chat_panel()
        launch_echoes = chat_panel.get_text_blocks().filter(has_text="launch-args:")
        expect(launch_echoes).to_have_count(1, timeout=_SETTLE_TIMEOUT_MS)
        expect(launch_echoes.first).to_contain_text("fast_mode=true effort=low resumed=yes")
        expect(chat_panel.get_error_block()).to_have_count(0)
