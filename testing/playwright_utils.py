from __future__ import annotations

import playwright
from loguru import logger
from playwright.sync_api import Page
from playwright.sync_api import expect
from tenacity import RetryError
from tenacity import retry
from tenacity import retry_if_exception_type
from tenacity import stop_after_delay
from tenacity import wait_fixed

from imbue_core.itertools import only
from sculptor.testing.elements.sidebar import PlaywrightSidebarElement
from sculptor.testing.elements.task import navigate_to_task_page
from sculptor.testing.elements.task_list import wait_for_tasks_to_build
from sculptor.testing.elements.task_starter import create_task
from sculptor.testing.pages.home_page import PlaywrightHomePage
from sculptor.testing.pages.settings_page import PlaywrightSettingsPage
from sculptor.testing.pages.task_page import PlaywrightTaskPage


def start_task_and_wait_for_ready(
    sculptor_page: Page, prompt: str, wait_for_agent_to_finish: bool = True
) -> PlaywrightTaskPage:
    # Navigate to the home page
    home_page = PlaywrightHomePage(page=sculptor_page)

    create_task(home_page.get_task_starter(), prompt)

    task_list = home_page.get_task_list()
    tasks = task_list.get_tasks()
    expect(tasks).to_have_count(1)

    wait_for_tasks_to_build(home_page.get_task_list())
    task = only(tasks.all())

    # We need to start a task and have the agent spin at least once to extract the state of MCP Servers
    task_page = navigate_to_task_page(task)

    if wait_for_agent_to_finish:
        # Ensure assistant has responded before continuing
        chat_panel = task_page.get_chat_panel()
        expect(chat_panel, "to finish outputting data").to_have_attribute("data-is-streaming", "false")

    return task_page


def navigate_to_frontend(page: Page, url: str, retry_seconds: float = 60) -> PlaywrightHomePage:
    base_url = url

    retry_goto = retry(
        stop=stop_after_delay(retry_seconds),
        wait=wait_fixed(1),
        retry=retry_if_exception_type(playwright.sync_api.Error),
        reraise=True,
    )(lambda: page.goto(base_url))

    try:
        retry_goto()
    except RetryError as e:
        logger.error(
            "Failed to load page at {base_url} after {retry_seconds}s: {e}",
            base_url=base_url,
            retry_seconds=retry_seconds,
            e=e,
        )
        raise

    return PlaywrightHomePage(page=page)


def navigate_to_settings_page(sidebar: PlaywrightSidebarElement, page: Page) -> PlaywrightSettingsPage:
    """Click the settings button to navigate to the settings page."""
    sidebar.get_settings_button().click()
    return PlaywrightSettingsPage(page=page)
