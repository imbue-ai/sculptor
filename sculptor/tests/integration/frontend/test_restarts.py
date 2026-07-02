import pytest
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import navigate_to_add_workspace_page
from sculptor.testing.playwright_utils import navigate_to_workspace
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story


@pytest.mark.skip(
    reason="The new-workspace form does not persist prompt drafts: the prompt is per-mount useState, reset on every open, so nothing survives a restart. The legacy TASK_INPUT testid this test drives also no longer renders; rewrite the test onto NEW_WORKSPACE_PROMPT_TEXTAREA if draft persistence lands."
)
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
        navigate_to_workspace(instance.page)
        task_page = PlaywrightTaskPage(page=instance.page)
        chat_panel = task_page.get_chat_panel()
        expect(chat_panel).to_be_visible()


@user_story("my progress to stay on backend restarts")
def test_chats_persist_on_restart(sculptor_instance_factory_: SculptorInstanceFactory) -> None:
    with sculptor_instance_factory_.spawn_instance() as instance:
        start_task_and_wait_for_ready(instance.page, prompt="Say hi to me")

    with sculptor_instance_factory_.spawn_instance() as instance:
        navigate_to_workspace(instance.page)
        task_page = PlaywrightTaskPage(page=instance.page)
        chat_panel = task_page.get_chat_panel()
        expect(chat_panel).to_be_visible()

        send_chat_message(chat_panel=chat_panel, message="Say bye to me")
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)
