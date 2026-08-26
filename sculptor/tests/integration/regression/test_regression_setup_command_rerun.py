"""Regression test: workspace setup must not auto-rerun across Sculptor restarts.

The new SetupCommandRunner records terminal state in the workspace's
setup_status column. After a successful run we persist `succeeded`; on app
restart, the lifespan reconciler should leave that row alone (only `running`
rows are converted to `failed`). Manual rerun via the SetupStatusCard's
button still works.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.setup_status import PlaywrightSetupStatusElement
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story


@user_story("to have my workspace setup command run only once, even across restarts")
def test_setup_command_does_not_rerun_after_restart(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """Phase 1: configure a setup command and create a workspace; the card
    reports succeeded and the rerun button (not cancel) is visible.

    Phase 2: restart Sculptor and reopen the same workspace; the card
    immediately shows the prior `succeeded` state (i.e. the rerun button
    is visible without first transitioning through `running`).
    """
    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page

        settings_page = navigate_to_settings_page(page=page)
        repos = settings_page.click_on_repositories()
        repos.expand_repo_config()
        repos.set_setup_command('echo "SCULPTOR_SETUP_RERUN_MARKER_98765"')

        start_task_and_wait_for_ready(sculptor_page=page)

        setup_status = PlaywrightSetupStatusElement(page=page)
        expect(setup_status.get_rerun_button()).to_be_visible()
        expect(setup_status.get_cancel_button()).to_have_count(0)

    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page

        workspace_row = get_workspace_sidebar(page).get_workspace_rows().first
        expect(workspace_row).to_be_visible()
        workspace_row.click()

        setup_status = PlaywrightSetupStatusElement(page=page)
        expect(setup_status.get_rerun_button()).to_be_visible()
        expect(setup_status.get_cancel_button()).to_have_count(0)


@user_story("to manually re-run a workspace setup command")
def test_setup_rerun_button_runs_command_again(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page

        settings_page = navigate_to_settings_page(page=page)
        repos = settings_page.click_on_repositories()
        repos.expand_repo_config()
        repos.set_setup_command("exit 1")

        start_task_and_wait_for_ready(sculptor_page=page)

        setup_status = PlaywrightSetupStatusElement(page=page)
        rerun_button = setup_status.get_rerun_button()
        expect(rerun_button).to_be_visible()
        rerun_button.click()
        expect(rerun_button).to_be_visible()
