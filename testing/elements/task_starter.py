from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightTaskStarterElement(PlaywrightIntegrationTestElement):
    def get_task_input(self) -> Locator:
        return self.get_by_test_id(ElementIDs.TASK_INPUT)

    def get_start_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.START_TASK_BUTTON)

    def get_branch_selector(self) -> Locator:
        return self.get_by_test_id(ElementIDs.BRANCH_SELECTOR)

    def get_branch_options(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.BRANCH_OPTION)

    def get_system_prompt_open_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.HOME_PAGE_SYSTEM_PROMPT_OPEN_BUTTON)

    def get_system_prompt_input_box(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.HOME_PAGE_SYSTEM_PROMPT_INPUT)

    def get_system_prompt_save_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.HOME_PAGE_SYSTEM_PROMPT_SAVE_BUTTON)


def create_task(task_starter: PlaywrightTaskStarterElement, task_text: str, branch_name: str | None = None) -> None:
    """Create a task without waiting for it to be ready."""
    if branch_name is not None:
        select_branch(task_starter, branch_name)

    task_input = task_starter.get_task_input()
    expect(task_input).to_have_attribute("contenteditable", "true")
    task_input.type(task_text)

    # FIXME: add this for sanity checking (Maciek had the .type lose a race to another operation)
    #        unfortunately the text gets stripped of newlines and reformatted so correct output
    #        does not equal input
    # expect(task_input).to_contain_text(task_text)

    expect(task_starter.get_start_button()).to_be_enabled()
    task_starter.get_start_button().click()


def select_branch(task_starter, branch_name: str, is_using_uncommitted_changes: bool = False) -> None:
    branch_selector = task_starter.get_branch_selector()
    branch_selector.click()
    branch_options = task_starter.get_branch_options()
    if is_using_uncommitted_changes:
        branch_option = branch_options.filter(has_text=branch_name).filter(has_text="*")
    else:
        branch_option = branch_options.filter(has_text=branch_name).filter(has_not_text="*")
    expect(branch_option).to_have_count(1)
    branch_option.click()
    expect(branch_selector).to_have_text(branch_name)


def set_home_page_system_prompt(task_starter, system_prompt: str) -> None:
    system_prompt_open_button = task_starter.get_system_prompt_open_button()
    system_prompt_open_button.click()
    system_prompt_input_box = task_starter.get_system_prompt_input_box()
    expect(system_prompt_input_box).to_be_visible()
    system_prompt_input_box.type(system_prompt)
    task_starter.get_system_prompt_save_button().click()
    expect(system_prompt_input_box).not_to_be_visible()
