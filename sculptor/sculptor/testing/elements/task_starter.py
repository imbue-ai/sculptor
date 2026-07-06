import re

from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement
from sculptor.testing.elements.file_preview_and_upload import PlaywrightFilePreviewAndUploadMixin


class PlaywrightTaskStarterElement(PlaywrightFilePreviewAndUploadMixin, PlaywrightIntegrationTestElement):
    def get_task_input(self) -> Locator:
        return self.get_by_test_id(ElementIDs.TASK_INPUT)

    def get_task_name_input(self) -> Locator:
        return self.get_by_test_id(ElementIDs.TASK_NAME_INPUT)

    def get_branch_selector(self) -> Locator:
        return self.get_by_test_id(ElementIDs.BRANCH_SELECTOR)

    def get_branch_options(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.BRANCH_OPTION)

    def get_task_mode_selector(self) -> Locator:
        return self.get_by_test_id(ElementIDs.MODE_SELECTOR)

    def get_workspace_selector(self) -> Locator:
        return self.get_by_test_id(ElementIDs.WORKSPACE_SELECTOR)

    def get_system_prompt_open_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.HOME_PAGE_SYSTEM_PROMPT_OPEN_BUTTON)

    def get_system_prompt_input_box(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.HOME_PAGE_SYSTEM_PROMPT_INPUT)

    def get_system_prompt_save_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.HOME_PAGE_SYSTEM_PROMPT_SAVE_BUTTON)


FAKE_CLAUDE_MODEL_NAME = "Fake Claude"
FAKE_CLAUDE_2_MODEL_NAME = "Fake Claude 2"
# Tag for the harness-parametrized integration fixture; pi selection flows
# through the per-agent type chosen at creation, not the model name.
FAKE_PI_MODEL_NAME = "Fake Pi"


def select_home_page_model(page: Page, model_name: str) -> None:
    """Select a model by exact name from the home page model selector.

    Uses Playwright's filter + expect to wait for the option to appear
    (testing-only models load asynchronously via WebSocket settings).
    """
    model_selector = page.get_by_test_id(ElementIDs.MODEL_SELECTOR)
    model_selector.click()
    target = page.get_by_test_id(re.compile(rf"^{re.escape(ElementIDs.MODEL_OPTION)}-")).filter(
        has=page.get_by_text(model_name, exact=True)
    )
    expect(target).to_be_visible(timeout=10_000)
    target.click()


def select_branch(
    task_starter: PlaywrightTaskStarterElement, branch_name: str, is_using_uncommitted_changes: bool = False
) -> None:
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


def select_task_mode(task_starter: PlaywrightTaskStarterElement, mode_option_id: str) -> None:
    """Select a task mode from the mode selector dropdown.

    Args:
        task_starter: The task starter element
        mode_option_id: The ElementIDs value for the mode option (e.g., ElementIDs.MODE_OPTION_CLONE)
    """
    mode_selector = task_starter.get_task_mode_selector()

    # Map mode option test IDs to their display labels
    mode_labels = {
        ElementIDs.MODE_OPTION_IN_PLACE: "In-place",
        ElementIDs.MODE_OPTION_CLONE: "Clone",
        ElementIDs.MODE_OPTION_EXISTING: "Existing",
    }
    target_label = mode_labels.get(mode_option_id)
    if target_label and target_label in (mode_selector.text_content() or ""):
        return

    mode_selector.click()
    mode_option = task_starter._page.get_by_test_id(mode_option_id)
    expect(mode_option).to_be_visible()
    mode_option.click()
    # Wait for the Radix UI Select dropdown to fully close. The dropdown portal
    # sets body.style.pointerEvents = "none" while open and restores it on close.
    # Without this wait, subsequent interactions can race with the close animation.
    expect(mode_option).not_to_be_visible()


def select_existing_workspace(task_starter: PlaywrightTaskStarterElement, workspace_description: str) -> None:
    """Select "existing workspace" mode and choose a specific workspace.

    Args:
        task_starter: The task starter element
        workspace_description: The description of the workspace to select
    """
    # First select "existing" mode
    select_task_mode(task_starter, ElementIDs.MODE_OPTION_EXISTING)

    # Then select the specific workspace from the workspace dropdown
    workspace_selector = task_starter.get_workspace_selector()
    workspace_selector.click()
    # Find the option whose WORKSPACE_OPTION_NAME child has the exact text.
    # We match on the nested test-id element rather than the option's accessible
    # name, because badges ("current", "1 agent") are included in the accessible
    # name and would break exact matching.
    workspace_option = task_starter._page.get_by_role("option").filter(
        has=task_starter._page.get_by_test_id(ElementIDs.WORKSPACE_OPTION_NAME).get_by_text(
            workspace_description, exact=True
        )
    )
    expect(workspace_option).to_have_count(1)
    workspace_option.click()


def set_home_page_system_prompt(task_starter: PlaywrightTaskStarterElement, system_prompt: str) -> None:
    system_prompt_open_button = task_starter.get_system_prompt_open_button()
    system_prompt_open_button.click()
    system_prompt_input_box = task_starter.get_system_prompt_input_box()
    expect(system_prompt_input_box).to_be_visible()
    system_prompt_input_box.fill(system_prompt)
    task_starter.get_system_prompt_save_button().click()
    expect(system_prompt_input_box).not_to_be_visible()
