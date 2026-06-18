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
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# A prompt that just sleeps — the agent stays busy with no output, so the chat
# status pill keeps showing its Stop button while setup runs concurrently.
_SLEEP_PROMPT = 'fake_claude:sleep `{"seconds": 120}`'


def _configure_setup_command(page: Page, command: str) -> None:
    settings_page = navigate_to_settings_page(page=page)
    repos = settings_page.click_on_repositories()
    repos.expand_repo_config()
    repos.set_setup_command(command)


def _best_effort_cancel_setup(setup_status: PlaywrightSetupStatusElement) -> None:
    """Cancel a still-running setup so a lingering ``sleep`` doesn't race the
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

    Repro shape: configure a long-running setup command (``sleep 60``) and
    start a turn that keeps the agent busy (``fake_claude:sleep``). Both run
    concurrently, so the chat status pill shows its Stop button while the setup
    card shows its running-only Cancel affordance. Clicking the chat Stop
    button must drive the setup command to a terminal state — the running-only
    Cancel affordance disappears and the terminal Rerun affordance appears.

    With the bug present, the Stop button only interrupts the agent: the setup
    subprocess keeps running, the card stays in its running state, and the
    Rerun affordance never appears.
    """
    page = sculptor_instance_.page
    _configure_setup_command(page, "sleep 60")

    setup_status = PlaywrightSetupStatusElement(page)
    try:
        task_page = start_task_and_wait_for_ready(
            sculptor_page=page,
            prompt=_SLEEP_PROMPT,
            wait_for_agent_to_finish=False,
        )
        chat_panel = task_page.get_chat_panel()

        # Precondition 1: the agent is mid-turn, so the chat Stop button is up.
        expect(chat_panel.get_thinking_indicator()).to_be_visible(timeout=15_000)
        stop_button = chat_panel.get_stop_button()
        expect(stop_button).to_be_visible()

        # Precondition 2: the setup command is running concurrently — the
        # running-only Cancel affordance proves it.
        expect(setup_status.get_cancel_button()).to_be_visible(timeout=30_000)

        # Act: click the chat Stop button.
        stop_button.click()

        # The setup command must terminate and the card must reflect the
        # stopped state: the running-only Cancel affordance disappears and the
        # terminal Rerun affordance appears. ``sleep 60`` would otherwise keep
        # the card in its running state well past this timeout.
        expect(setup_status.get_rerun_button()).to_be_visible(timeout=20_000)
        expect(setup_status.get_cancel_button()).to_have_count(0)
    finally:
        _best_effort_cancel_setup(setup_status)
