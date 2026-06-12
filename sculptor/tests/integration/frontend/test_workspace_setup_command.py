"""Integration tests for the workspace setup command feature.

Tests cover:
- Setup command input visibility in Settings > Repositories
- Saving setup command on blur
- Setup command running when a CLONE workspace is created (asserted via the
  pinned SetupStatusCard, not the legacy PTY terminal tab)
- The CTA card is shown when no setup command is configured
"""

import re

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.setup_status import PlaywrightSetupStatusElement
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to configure a workspace setup command")
def test_setup_command_input_visible_in_settings(sculptor_instance_: SculptorInstance) -> None:
    """The setup command input should be visible in Settings > Repositories, pre-filled with the default."""
    page = sculptor_instance_.page

    settings_page = navigate_to_settings_page(page=page)
    repos = settings_page.click_on_repositories()
    repos.expand_repo_config()

    setup_input = repos.get_setup_command_input()
    expect(setup_input).to_be_visible()
    # A freshly-added project tracks the current default, which is displayed in the textarea.
    expect(setup_input).to_have_value("git fetch origin 2>/dev/null || true")


@user_story("to configure a workspace setup command")
def test_setup_command_saves_on_blur(sculptor_instance_: SculptorInstance) -> None:
    """Typing a setup command and blurring should persist the value across page reloads."""
    page = sculptor_instance_.page

    settings_page = navigate_to_settings_page(page=page)
    settings_page.click_on_repositories().expand_repo_config()
    setup_input = page.get_by_test_id(ElementIDs.SETTINGS_WORKSPACE_SETUP_COMMAND_INPUT).first
    expect(setup_input).to_be_visible()

    setup_input.fill("echo test-persist")
    setup_input.blur()
    page.wait_for_timeout(500)

    settings_page = navigate_to_settings_page(page=page)
    settings_page.click_on_repositories().expand_repo_config()
    setup_input = page.get_by_test_id(ElementIDs.SETTINGS_WORKSPACE_SETUP_COMMAND_INPUT).first
    expect(setup_input).to_be_visible()
    expect(setup_input).to_have_value("echo test-persist")


@user_story("to have my workspace automatically set up when created")
def test_setup_command_runs_in_new_workspace(sculptor_instance_: SculptorInstance) -> None:
    """Creating a CLONE workspace with a setup command should produce a SetupStatusCard
    that streams the command's output and ends in succeeded."""
    page = sculptor_instance_.page

    settings_page = navigate_to_settings_page(page=page)
    repos = settings_page.click_on_repositories()
    repos.expand_repo_config()
    repos.set_setup_command('echo "SCULPTOR_SETUP_MARKER_12345"')

    start_task_and_wait_for_ready(sculptor_page=page)

    setup = PlaywrightSetupStatusElement(page=page)
    expect(setup.get_card()).to_be_visible()
    # The queued card mirrors its readiness via `aria-disabled`, so this click
    # auto-waits for the run to start and the popover trigger to mount (SCU-1215).
    setup.get_card().click()
    expect(setup.get_output()).to_contain_text("SCULPTOR_SETUP_MARKER_12345")


@user_story("to be prompted to configure a setup command when none is set")
def test_no_card_when_command_is_empty(sculptor_instance_: SculptorInstance) -> None:
    """Creating a workspace without a setup command should show the config-prompt CTA
    (the card returns the existing CTA for not_configured workspaces)."""
    page = sculptor_instance_.page

    settings_page = navigate_to_settings_page(page=page)
    repos = settings_page.click_on_repositories()
    repos.expand_repo_config()
    repos.set_setup_command("")

    start_task_and_wait_for_ready(sculptor_page=page)

    setup = PlaywrightSetupStatusElement(page=page)
    expect(setup.get_config_prompt()).to_be_visible()
    expect(setup.get_card()).to_have_count(0)


@user_story("to quick-edit my setup command from the agent page")
def test_setup_edit_button_visible_in_status_card(sculptor_instance_: SculptorInstance) -> None:
    """The pencil edit button should be visible in the alpha SetupStatusCard."""
    page = sculptor_instance_.page

    settings_page = navigate_to_settings_page(page=page)
    repos = settings_page.click_on_repositories()
    repos.expand_repo_config()
    repos.set_setup_command('echo "SCULPTOR_SETUP_MARKER_QUICKEDIT"')

    start_task_and_wait_for_ready(sculptor_page=page)

    setup = PlaywrightSetupStatusElement(page=page)
    expect(setup.get_card()).to_be_visible()
    expect(setup.get_edit_button()).to_be_visible()


@user_story("to land on the focused textarea after clicking edit")
def test_setup_edit_button_deep_links_to_focused_textarea(sculptor_instance_: SculptorInstance) -> None:
    """Clicking the pencil edit button should navigate to settings with the matching repo
    auto-expanded and the setup-command textarea focused."""
    page = sculptor_instance_.page

    settings_page = navigate_to_settings_page(page=page)
    repos = settings_page.click_on_repositories()
    repos.expand_repo_config()
    repos.set_setup_command('echo "SCULPTOR_SETUP_MARKER_QUICKEDIT"')

    start_task_and_wait_for_ready(sculptor_page=page)

    setup = PlaywrightSetupStatusElement(page=page)
    expect(setup.get_card()).to_be_visible()
    setup.get_edit_button().click()

    expect(page).to_have_url(re.compile(r".*section=repositories.*focusRepo=.*"))

    textarea = repos.get_setup_command_input()
    expect(textarea).to_be_visible()
    expect(textarea).to_be_focused()


@user_story("to land on the focused textarea from the configure-CTA")
def test_setup_config_prompt_deep_links_to_focused_textarea(sculptor_instance_: SculptorInstance) -> None:
    """Clicking the SetupConfigPrompt CTA should deep-link to settings with the matching
    repo auto-expanded and the setup-command textarea focused."""
    page = sculptor_instance_.page

    settings_page = navigate_to_settings_page(page=page)
    repos = settings_page.click_on_repositories()
    repos.expand_repo_config()
    repos.set_setup_command("")

    start_task_and_wait_for_ready(sculptor_page=page)

    setup = PlaywrightSetupStatusElement(page=page)
    expect(setup.get_config_prompt()).to_be_visible()
    setup.get_config_settings_link().click()

    expect(page).to_have_url(re.compile(r".*section=repositories.*focusRepo=.*"))

    textarea = repos.get_setup_command_input()
    expect(textarea).to_be_visible()
    expect(textarea).to_be_focused()
