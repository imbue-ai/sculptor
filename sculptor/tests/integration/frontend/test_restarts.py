import pytest
from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.pages.new_workspace_modal_page import PlaywrightNewWorkspaceModalPage
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import open_new_workspace_modal
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

SECONDS_MS = 1000

# Workspace tabs may take longer to appear after a restart because the
# new Electron process needs to load, fetch workspace data from the API,
# and render the tabs.
_RESTART_VISIBILITY_TIMEOUT_MS = 10 * SECONDS_MS


@pytest.mark.skip(
    reason="NewWorkspaceModal's draft atoms persist within session but are not serialized across app restarts"
)
@user_story("my selections to stay on backend restarts")
def test_home_page_prompts_persist_on_restart(sculptor_instance_factory_: SculptorInstanceFactory) -> None:
    prompt_text = "This prompt should persist across restarts"

    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        open_new_workspace_modal(page)
        modal = PlaywrightNewWorkspaceModalPage(page=page)
        task_input = modal.get_task_input()
        expect(task_input).to_have_attribute("contenteditable", "true")
        task_input.click()
        task_input.fill(prompt_text)

    with sculptor_instance_factory_.spawn_instance() as instance:
        open_new_workspace_modal(instance.page)
        modal = PlaywrightNewWorkspaceModalPage(page=instance.page)
        task_input = modal.get_task_input()
        expect(task_input).to_have_text(prompt_text)


@user_story("my progress to stay on backend restarts")
def test_tasks_persist_on_restart(sculptor_instance_factory_: SculptorInstanceFactory) -> None:
    with sculptor_instance_factory_.spawn_instance() as instance:
        task_page = start_task_and_wait_for_ready(instance.page, prompt="Say hi to me")
        chat_panel = task_page.get_chat_panel()
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    with sculptor_instance_factory_.spawn_instance() as instance:
        layout = PlaywrightProjectLayoutPage(page=instance.page)
        workspace_tab = layout.get_workspace_tabs().first
        expect(workspace_tab).to_be_visible(timeout=_RESTART_VISIBILITY_TIMEOUT_MS)
        workspace_tab.click()
        task_page = PlaywrightTaskPage(page=instance.page)
        chat_panel_locator = task_page.get_chat_panel()
        expect(chat_panel_locator).to_be_visible(timeout=_RESTART_VISIBILITY_TIMEOUT_MS)


@user_story("my progress to stay on backend restarts")
def test_chats_persist_on_restart(sculptor_instance_factory_: SculptorInstanceFactory) -> None:
    with sculptor_instance_factory_.spawn_instance() as instance:
        start_task_and_wait_for_ready(instance.page, prompt="Say hi to me")

    with sculptor_instance_factory_.spawn_instance() as instance:
        task_page = PlaywrightTaskPage(page=instance.page)
        workspace_tab = task_page.get_workspace_tabs().first
        expect(workspace_tab).to_be_visible(timeout=_RESTART_VISIBILITY_TIMEOUT_MS)
        workspace_tab.click()
        chat_panel = task_page.get_chat_panel()
        expect(chat_panel).to_be_visible(timeout=_RESTART_VISIBILITY_TIMEOUT_MS)

        send_chat_message(chat_panel=chat_panel, message="Say bye to me")
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)


# ``test_restart_reuses_existing_new_workspace_tab`` was removed with the
# modal migration. It asserted that an "Open Workspace" pseudo-tab in the
# tab bar persisted across restarts — but the modal flow has no such
# pseudo-tab. The new equivalent (a fresh boot with no workspaces lands on
# /home, which renders the inline new-workspace form) is exercised
# implicitly any time a spawn_instance test starts from an empty state and
# navigates to "/".
#
# ``test_restart_opens_existing_workspace_when_mru_missing`` was also
# removed: it relied on the backend MRU file (now superseded by the
# localStorage-based ``sculptor-tabs`` state), and the rootLoader no
# longer falls back to "list recent workspaces" — it redirects empty
# sessions to /home (where the inline new-workspace form renders) instead.
