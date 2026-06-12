"""Session-resume behavior for the pi harness, under FakePi.

Pi persists a per-task JSONL session (``--session-dir``/``--session-id``); a
relaunched agent process resumes it, so a conversation survives a Sculptor
restart (``supports_session_resume``). These tests use the restart factory —
the cleanest agent-process-restart lever for pi, which has no UI Stop button
(``supports_interruption`` is false) — to plant content, restart the whole
instance, and assert the resumed agent recalls it.

FakePi's ``fake_pi:recall`` directive echoes the user messages it reloaded from
the persisted session, so a successful recall proves the resume wired all the
way through PiAgent's ``--session-id`` relaunch.
"""

from playwright.sync_api import expect

from sculptor.interfaces.agents.agent import HarnessName
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.fake_pi import install_fake_pi_binary
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

_SENTINEL = "PINEAPPLE-77"


@user_story("my pi conversation to survive a Sculptor restart and answer follow-ups from prior context")
def test_pi_session_resumes_prior_context_across_restart(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    # Instance 1: plant a codeword and let the turn complete (so it is persisted
    # to pi's session file under the per-task state dir).
    with sculptor_instance_factory_.spawn_instance() as instance:
        install_fake_pi_binary(instance.fake_bin_dir)
        task_page = start_task_and_wait_for_ready(
            sculptor_page=instance.page,
            workspace_name="Pi Resume",
            model_name=None,
            harness=HarnessName.PI,
            prompt=f"Remember the codeword {_SENTINEL}.",
        )
        chat_panel = task_page.get_chat_panel()
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Instance 2: the backend (and the pi agent process) restarts. Re-opening the
    # workspace re-runs the agent, which resumes the persisted session via
    # --session-id; `fake_pi:recall` then reproduces the pre-restart codeword.
    with sculptor_instance_factory_.spawn_instance() as instance:
        install_fake_pi_binary(instance.fake_bin_dir)
        layout = PlaywrightProjectLayoutPage(page=instance.page)
        workspace_tab = layout.get_workspace_tabs().first
        expect(workspace_tab).to_be_visible()
        workspace_tab.click()
        task_page = PlaywrightTaskPage(page=instance.page)
        chat_panel = task_page.get_chat_panel()
        expect(chat_panel).to_be_visible()

        send_chat_message(chat_panel=chat_panel, message="fake_pi:recall")
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)
        # The resumed agent recalled the codeword from the pre-restart session.
        expect(chat_panel.get_assistant_messages().last).to_contain_text(_SENTINEL)


@user_story("a fresh pi workspace to start with no leaked prior context")
def test_pi_fresh_workspace_has_no_prior_context(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    # A brand-new workspace (no persisted session id) must start a clean session:
    # recall finds nothing, proving no stale context bleeds into a fresh task.
    with sculptor_instance_factory_.spawn_instance() as instance:
        install_fake_pi_binary(instance.fake_bin_dir)
        task_page = start_task_and_wait_for_ready(
            sculptor_page=instance.page,
            workspace_name="Pi Fresh",
            model_name=None,
            harness=HarnessName.PI,
            prompt="fake_pi:recall",
        )
        chat_panel = task_page.get_chat_panel()
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)
        expect(chat_panel.get_assistant_messages().last).to_contain_text("NO_PRIOR_CONTEXT")
