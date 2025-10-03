from playwright.sync_api import Locator
from playwright.sync_api import expect

from imbue_core.itertools import only
from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightTaskModalElement(PlaywrightIntegrationTestElement):
    def get_input_element(self) -> Locator:
        """Get the prompt input element in the task modal."""
        return self.get_by_test_id(ElementIDs.TASK_MODAL_INPUT)

    def close(self):
        """Close the task modal."""
        self.get_by_test_id(ElementIDs.TASK_MODAL_CLOSE_BUTTON).click()
        expect(self).not_to_be_visible()

    def start_task(self):
        """Start the task from the task modal."""
        button = self.get_by_test_id(ElementIDs.TASK_MODAL_CREATE_TASK_BUTTON)
        expect(button).to_contain_text("Start Task")
        expect(button).to_be_enabled()
        button.click()

    def fork_task(self):
        """Fork the task from the task modal (same button as start_task, but in fork mode)."""
        button = self.get_by_test_id(ElementIDs.TASK_MODAL_CREATE_TASK_BUTTON)
        expect(button).to_contain_text("Fork Task")
        expect(button).to_be_enabled()
        button.click()

    def toggle_create_more(self):
        self.get_by_test_id(ElementIDs.TASK_MODAL_CREATE_MORE_TOGGLE).click()

    def switch_source_branch(self, branch_name: str):
        """Switch the source branch in the task modal."""
        branch_selector = self.get_by_test_id(ElementIDs.BRANCH_SELECTOR)
        branch_selector.click()
        expect(branch_selector).to_be_visible()
        branches = self.page.get_by_test_id(ElementIDs.BRANCH_OPTION)
        branch_to_switch_to = only([branch for branch in branches.all() if branch.inner_text() == branch_name])
        branch_to_switch_to.click()

    def get_system_prompt_text(self) -> str:
        """Get the system prompt text from the task modal."""
        self.get_by_test_id(ElementIDs.TASK_MODAL_SYSTEM_PROMPT_OPEN_BUTTON).click()
        input_element = self.get_input_element()
        expect(input_element).to_be_visible()
        system_prompt_text = input_element.inner_text().strip()
        self.get_by_test_id(ElementIDs.TASK_MODAL_SYSTEM_PROMPT_CANCEL_BUTTON).click()
        return system_prompt_text

    def update_system_prompt(self, new_system_prompt: str):
        """Click the update system prompt button in the task modal, then type in the system prompt input, then click save."""
        self.get_by_test_id(ElementIDs.TASK_MODAL_SYSTEM_PROMPT_OPEN_BUTTON).click()
        self.get_input_element().click()
        self.get_input_element().clear()
        self.get_input_element().fill(new_system_prompt)
        self.get_by_test_id(ElementIDs.TASK_MODAL_SYSTEM_PROMPT_SAVE_BUTTON).click()

    def get_model_selector(self) -> Locator:
        """Get the model selector dropdown in the task modal."""
        return self.get_by_test_id(ElementIDs.TASK_MODAL_MODEL_SELECTOR)
