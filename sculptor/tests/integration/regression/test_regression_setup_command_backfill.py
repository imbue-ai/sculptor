"""Regression test: enabling the workspace-setup-commands toggle must not
retroactively run setup in workspaces that were created before the toggle.

Bug history: When the toggle was enabled after a workspace already existed,
the legacy implementation injected the setup command into that workspace's
existing PTY on the very next Sculptor restart. The new SetupCommandRunner
records `setup_status` per workspace at creation time; pre-existing rows
are backfilled to `succeeded` (or `not_configured`) by the alembic data
migration, so the runner never auto-fires on them. This test exercises the
end-to-end flow:

1. Start Sculptor with the toggle off; create a workspace.
2. Enable the toggle and configure a workspace setup command.
3. Restart Sculptor.
4. Reopen the pre-existing workspace and assert the setup card never enters
   `running` (the cancel button never appears) — i.e. the command did not
   auto-fire retroactively.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.setup_status import PlaywrightSetupStatusElement
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story


@user_story("to not have setup commands run retroactively on my existing workspaces")
def test_setup_command_does_not_run_in_preexisting_workspace(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    # Phase 1: clear the project's setup command, create a workspace
    # (born "not_configured"), then configure a command.
    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page

        # Clear the project's command first so the workspace is created
        # with setup_status="not_configured" (no command to resolve).
        settings_page = navigate_to_settings_page(page=page)
        repos = settings_page.click_on_repositories()
        repos.expand_repo_config()
        setup_input = repos.get_setup_command_input()
        expect(setup_input).to_be_visible()
        setup_input.fill("")
        with page.expect_response(
            lambda r: "workspace_setup_command" in r.url and r.request.method == "PUT"
        ) as response_info:
            setup_input.blur()
        assert response_info.value.ok, f"setup command clear failed: {response_info.value.status}"

        start_task_and_wait_for_ready(page, prompt="Say hi to me")

        # Configure a setup command, then shut down.
        settings_page = navigate_to_settings_page(page=page)
        repos = settings_page.click_on_repositories()
        repos.expand_repo_config()
        setup_input = repos.get_setup_command_input()
        expect(setup_input).to_be_visible()
        setup_input.fill("echo SCULPTOR_SETUP_BACKFILL_MARKER_54321")
        with page.expect_response(
            lambda r: "workspace_setup_command" in r.url and r.request.method == "PUT"
        ) as response_info:
            setup_input.blur()
        assert response_info.value.ok, f"setup command save failed: {response_info.value.status}"

    # Phase 2: restart with toggle on and setup command configured. The
    # pre-existing workspace was created with setup_status="not_configured"
    # (toggle was off at creation time) — flipping the toggle on later must
    # not retroactively change that to "pending" and trigger a run. Because
    # the project now has a configured command, the card offers a manual
    # Run-setup affordance instead of auto-firing — the regression we're
    # guarding is "never auto-run", so the cancel button must never appear.
    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page

        workspace_row = get_workspace_sidebar(page).get_workspace_rows().first
        expect(workspace_row).to_be_visible()
        workspace_row.click()

        setup_status = PlaywrightSetupStatusElement(page)
        expect(setup_status.get_run_button()).to_be_visible()
        expect(setup_status.get_cancel_button()).to_have_count(0)
        expect(setup_status.get_rerun_button()).to_have_count(0)
