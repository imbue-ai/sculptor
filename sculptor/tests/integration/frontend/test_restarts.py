from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import navigate_to_workspace
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story


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
