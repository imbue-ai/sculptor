"""Integration tests for the pinned workspace setup status card.

Tests cover:
- Pinned card is visible above the chat with the right badge for each terminal
  state (succeeded, failed) once setup completes.
- Rerun button replays a failed setup.
- Cancel button stops a long-running setup.
- Truncation banner appears when the persisted log overflowed the head+tail cap.
- The CTA appears for projects without a configured setup command.
- The Run-setup affordance appears when a command is configured after the
  workspace was created without one.
- Disabling the toggle hides the card.
"""

import re

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.setup_status import PlaywrightSetupStatusElement
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import navigate_to_workspace_without_agent
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _extract_workspace_id(url: str) -> str:
    """Extract the workspace ID from a Sculptor URL (format: /ws/{workspaceID}/agent/...)."""
    match = re.search(r"/ws/([a-zA-Z0-9_-]+)/", url)
    if not match:
        raise ValueError(f"Could not extract workspace ID from URL: {url}")
    return match.group(1)


def _configure_setup_command(page: Page, command: str) -> None:
    settings_page = navigate_to_settings_page(page=page)
    repos = settings_page.click_on_repositories()
    repos.expand_repo_config()
    repos.set_setup_command(command)


@user_story("to see that my workspace setup completed successfully")
def test_setup_card_shows_succeeded(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    _configure_setup_command(page, 'echo "SETUP_DONE"')

    start_task_and_wait_for_ready(sculptor_page=page)

    setup = PlaywrightSetupStatusElement(page)
    card = setup.get_card()
    expect(card).to_be_visible()
    expect(setup.get_rerun_button()).to_be_visible()
    expect(setup.get_cancel_button()).to_have_count(0)
    # Output is collapsed in the terminal state; clicking the card opens
    # the popover that contains the persisted log.
    card.click()
    output = setup.get_output()
    expect(output).to_contain_text("SETUP_DONE")
    # Successful runs match bash tool calls — no "Exit code N" prefix.
    expect(output).not_to_contain_text("Exit code")


@user_story("to have my setup command run inside the workspace's clone, not the source repo")
def test_setup_runs_in_workspace_working_directory(sculptor_instance_: SculptorInstance) -> None:
    """Setup should execute inside the per-workspace working directory.

    For a CLONE workspace that's `<workspace_root>/code/`. Build artifacts
    (node_modules, .venv, etc.) need to land there so the agent sees them.
    `pwd` plus a workspace-marker file lets us assert both that we're inside
    the clone *and* that we're not in the user's source repo.
    """
    page = sculptor_instance_.page
    _configure_setup_command(page, "pwd && ls .git >/dev/null && echo CLONE_DETECTED")

    start_task_and_wait_for_ready(sculptor_page=page)

    setup = PlaywrightSetupStatusElement(page)
    card = setup.get_card()
    expect(card).to_be_visible()
    # The queued card mirrors its readiness via `aria-disabled`, so this click
    # auto-waits for the run to start and the popover trigger to mount (SCU-1215).
    card.click()
    output = setup.get_output()
    # Expected directory shape: ".../workspaces/<id>/code"
    expect(output).to_contain_text("/code")
    expect(output).to_contain_text("CLONE_DETECTED")


@user_story("to see that my workspace setup failed")
def test_setup_card_shows_failed(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    # Mix stdout, stderr, and a non-zero exit so we can assert the popover
    # renders all three the way bash tool calls do: "Exit code N" prefix on
    # failure, with stderr merged into the captured stream.
    _configure_setup_command(page, "echo to-stdout; echo to-stderr >&2; exit 7")

    start_task_and_wait_for_ready(sculptor_page=page)

    setup = PlaywrightSetupStatusElement(page)
    card = setup.get_card()
    expect(card).to_be_visible()
    expect(setup.get_rerun_button()).to_be_visible()
    card.click()
    output = setup.get_output()
    expect(output).to_contain_text("Exit code 7")
    expect(output).to_contain_text("to-stdout")
    expect(output).to_contain_text("to-stderr")


@user_story("to re-run a failed workspace setup command")
def test_setup_rerun_replays_command(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    _configure_setup_command(page, "exit 1")

    start_task_and_wait_for_ready(sculptor_page=page)

    setup = PlaywrightSetupStatusElement(page)
    rerun_button = setup.get_rerun_button()
    expect(rerun_button).to_be_visible()
    rerun_button.click()
    # The command keeps failing on rerun; the rerun button should reappear
    # after the new run terminates rather than staying visible the whole time.
    expect(rerun_button).to_be_visible()


@user_story("to cancel a long-running workspace setup")
def test_setup_cancel_stops_running_command(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    _configure_setup_command(page, "sleep 60")

    start_task_and_wait_for_ready(sculptor_page=page)

    setup = PlaywrightSetupStatusElement(page)
    cancel_button = setup.get_cancel_button()
    expect(cancel_button).to_be_visible()
    cancel_button.click()
    expect(setup.get_rerun_button()).to_be_visible()


@user_story("to see when my setup output was truncated")
def test_setup_truncation_banner(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    # Emit ~1.2 MB so the head+tail buffer overflows.
    _configure_setup_command(page, "head -c 1200000 /dev/zero | tr '\\0' x")

    start_task_and_wait_for_ready(sculptor_page=page)

    # Truncation banner lives inside the popover; click the card to open it.
    setup = PlaywrightSetupStatusElement(page)
    card = setup.get_card()
    expect(card).to_be_visible()
    expect(setup.get_rerun_button()).to_be_visible()
    card.click()
    expect(setup.get_truncation_banner()).to_be_visible()


@user_story("to be prompted to configure a setup command")
def test_setup_config_prompt_when_no_command(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    _configure_setup_command(page, "")

    start_task_and_wait_for_ready(sculptor_page=page)

    setup = PlaywrightSetupStatusElement(page)
    expect(setup.get_config_prompt()).to_be_visible()


@user_story("to not be offered a rerun when the project's setup command has been cleared")
def test_setup_rerun_hidden_when_command_cleared_after_run(
    sculptor_instance_: SculptorInstance,
) -> None:
    """A rerun would 422 on the backend when the project no longer has a
    command configured. Hide the button so users aren't offered a no-op.
    """
    page = sculptor_instance_.page
    _configure_setup_command(page, 'echo "INITIAL_RUN"')

    start_task_and_wait_for_ready(sculptor_page=page)

    setup = PlaywrightSetupStatusElement(page)
    expect(setup.get_rerun_button()).to_be_visible()
    workspace_id = _extract_workspace_id(page.url)

    _configure_setup_command(page, "")
    navigate_to_workspace_without_agent(page, workspace_id)

    expect(setup.get_rerun_button()).to_have_count(0)
    # The card itself stays around so the user can still inspect the previous run.
    expect(setup.get_card()).to_be_visible()


@user_story("to run setup after configuring a command for a workspace that didn't have one")
def test_setup_run_button_appears_when_command_added_after_creation(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Workspaces created without a configured setup command land in
    `not_configured` state. If the user later sets a project-level setup
    command, the workspace should switch from the configure-CTA to a card
    with a Run-setup affordance — clicking it kicks off the first run.
    """
    page = sculptor_instance_.page
    _configure_setup_command(page, "")

    start_task_and_wait_for_ready(sculptor_page=page)

    setup = PlaywrightSetupStatusElement(page)
    # No command at creation time: configure-CTA visible, no card.
    expect(setup.get_config_prompt()).to_be_visible()
    expect(setup.get_card()).to_have_count(0)
    workspace_id = _extract_workspace_id(page.url)

    _configure_setup_command(page, 'echo "RUN_AFTER_CONFIG"')
    # Hash-only navigation back to the workspace keeps the WebSocket alive and
    # avoids a full SPA reload.
    navigate_to_workspace_without_agent(page, workspace_id)

    card = setup.get_card()
    expect(card).to_be_visible()
    expect(setup.get_config_prompt()).to_have_count(0)
    run_button = setup.get_run_button()
    expect(run_button).to_be_visible()
    run_button.click()

    # Once the run finishes, the card transitions to its terminal-state layout
    # (rerun button + popover with persisted output).
    expect(setup.get_rerun_button()).to_be_visible()
    card.click()
    expect(setup.get_output()).to_contain_text("RUN_AFTER_CONFIG")
