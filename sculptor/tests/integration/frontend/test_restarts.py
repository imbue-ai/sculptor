import pytest
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.pages.add_workspace_page import PlaywrightAddWorkspacePage
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import navigate_to_add_workspace_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story


@pytest.mark.skip(reason="AddWorkspacePage does not persist prompt drafts yet (useNewTaskPromptDraft is unused)")
@user_story("my selections to stay on backend restarts")
def test_home_page_prompts_persist_on_restart(sculptor_instance_factory_: SculptorInstanceFactory) -> None:
    prompt_text = "This prompt should persist across restarts"

    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        navigate_to_add_workspace_page(page)
        task_input = page.get_by_test_id(ElementIDs.TASK_INPUT)
        expect(task_input).to_have_attribute("contenteditable", "true")
        task_input.click()
        task_input.fill(prompt_text)

    with sculptor_instance_factory_.spawn_instance() as instance:
        navigate_to_add_workspace_page(instance.page)
        task_input = instance.page.get_by_test_id(ElementIDs.TASK_INPUT)
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
        expect(workspace_tab).to_be_visible()
        workspace_tab.click()
        task_page = PlaywrightTaskPage(page=instance.page)
        chat_panel = task_page.get_chat_panel()
        expect(chat_panel).to_be_visible()


@user_story("my progress to stay on backend restarts")
def test_chats_persist_on_restart(sculptor_instance_factory_: SculptorInstanceFactory) -> None:
    with sculptor_instance_factory_.spawn_instance() as instance:
        start_task_and_wait_for_ready(instance.page, prompt="Say hi to me")

    with sculptor_instance_factory_.spawn_instance() as instance:
        layout = PlaywrightProjectLayoutPage(page=instance.page)
        workspace_tab = layout.get_workspace_tabs().first
        expect(workspace_tab).to_be_visible()
        workspace_tab.click()
        task_page = PlaywrightTaskPage(page=instance.page)
        chat_panel = task_page.get_chat_panel()
        expect(chat_panel).to_be_visible()

        send_chat_message(chat_panel=chat_panel, message="Say bye to me")
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)


@user_story("my new workspace tab to persist on restart")
def test_restart_reuses_existing_new_workspace_tab(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """Restarting without creating a workspace should reuse the existing new-workspace tab, not add another."""
    with sculptor_instance_factory_.spawn_instance() as instance:
        add_workspace = PlaywrightAddWorkspacePage(page=instance.page)

        # We land on the add-workspace page (no workspaces exist yet)
        expect(add_workspace.get_submit_button()).to_be_visible()

        # There should be exactly one new-workspace tab
        expect(add_workspace.get_add_workspace_tabs()).to_have_count(1)

    # Restart — the rootLoader should reuse the existing new-workspace pseudo-tab
    with sculptor_instance_factory_.spawn_instance() as instance:
        add_workspace = PlaywrightAddWorkspacePage(page=instance.page)

        expect(add_workspace.get_submit_button()).to_be_visible()

        # Still exactly one new-workspace tab — not two
        expect(add_workspace.get_add_workspace_tabs()).to_have_count(1)
