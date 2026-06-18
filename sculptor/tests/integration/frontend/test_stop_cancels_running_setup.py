"""Test that the chat Stop button terminates a running workspace setup command.

When a workspace setup command is still running while the agent is mid-turn,
the chat status pill shows a Stop button. Clicking it must terminate the
in-progress setup command (not just interrupt the agent) and the setup card
must reflect the stopped/terminal state.

See SCU-1527.
"""

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.setup_status import PlaywrightSetupStatusElement
from sculptor.testing.fake_claude_pause import FakeClaudePause
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# A setup command that runs effectively forever, so it can never finish on its
# own within the test window — the only way the card leaves its running state
# is the Stop button (the behaviour under test) or the cleanup cancel. A short
# sleep could complete naturally on a slow runner and mask the bug.
_LONG_SETUP_COMMAND = "sleep 600"


def _configure_setup_command(page: Page, command: str) -> None:
    settings_page = navigate_to_settings_page(page=page)
    repos = settings_page.click_on_repositories()
    repos.expand_repo_config()
    repos.set_setup_command(command)


def _best_effort_cancel_setup(setup_status: PlaywrightSetupStatusElement) -> None:
    """Cancel a still-running setup so the long-lived ``sleep`` doesn't race the
    Playwright trace teardown (mirrors the setup-reminder tests). Best-effort:
    if setup already terminated, the cancel button is gone and there's nothing
    to do."""
    cancel_button = setup_status.get_cancel_button()
    if cancel_button.count() > 0 and cancel_button.is_visible():
        cancel_button.click()


@user_story("to terminate a running workspace setup command by clicking the chat Stop button")
def test_stop_button_cancels_running_setup_command(sculptor_instance_: SculptorInstance) -> None:
    """Clicking the chat Stop button while a setup command is running must
    terminate the setup command and surface the stopped state in the setup
    card.

    Repro shape: configure a long-running setup command and start a turn that
    keeps the agent busy (a ``FakeClaudePause`` sentinel, so the agent stays
    mid-turn with no wall-clock race). Both run concurrently, so the chat
    status pill shows its Stop button while the setup card shows its
    running-only Cancel affordance. Clicking the chat Stop button must drive
    the setup command to a terminal state — the running-only Cancel affordance
    disappears and the terminal Rerun affordance appears.

    With the bug present, the Stop button only interrupts the agent: the setup
    subprocess keeps running, the card stays in its running state, and the
    Rerun affordance never appears.
    """
    page = sculptor_instance_.page
    _configure_setup_command(page, _LONG_SETUP_COMMAND)

    setup_status = PlaywrightSetupStatusElement(page)
    pause = FakeClaudePause()
    try:
        task_page = start_task_and_wait_for_ready(
            sculptor_page=page,
            prompt=pause.prompt,
            wait_for_agent_to_finish=False,
        )
        chat_panel = task_page.get_chat_panel()

        # Precondition 1: the agent is mid-turn, so the chat Stop button is up.
        expect(chat_panel.get_thinking_indicator()).to_be_visible()
        stop_button = chat_panel.get_stop_button()
        expect(stop_button).to_be_visible()

        # Precondition 2: the setup command is running concurrently — the
        # running-only Cancel affordance proves it.
        expect(setup_status.get_cancel_button()).to_be_visible()

        # Act: click the chat Stop button.
        stop_button.click()

        # The setup command must terminate and the card must reflect the
        # stopped state: the running-only Cancel affordance disappears and the
        # terminal Rerun affordance appears.
        expect(setup_status.get_rerun_button()).to_be_visible()
        expect(setup_status.get_cancel_button()).to_have_count(0)
    finally:
        # Let the paused agent turn end naturally (Stop already killed it; this
        # is belt-and-suspenders) and kill any setup left running on failure.
        pause.release()
        _best_effort_cancel_setup(setup_status)
