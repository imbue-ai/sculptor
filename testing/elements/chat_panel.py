from playwright.sync_api import Locator
from playwright.sync_api import expect

from imbue_core.itertools import only
from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement
from sculptor.testing.elements.feedback_buttons import PlaywrightFeedbackButtonsElement
from sculptor.testing.elements.feedback_dialog import PlaywrightFeedbackDialogElement


class PlaywrightChatPanelElement(PlaywrightIntegrationTestElement):
    def get_chat_input(self) -> Locator:
        return self.get_by_test_id(ElementIDs.CHAT_INPUT)

    def get_send_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SEND_BUTTON)

    def get_stop_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.STOP_BUTTON)

    def get_stop_button_spinner(self) -> Locator:
        return self.get_by_test_id(ElementIDs.STOP_BUTTON_SPINNER)

    def get_tool_call(self) -> Locator:
        return self.get_by_test_id(ElementIDs.TOOL_CALL)

    def get_context_summary_messages(self) -> Locator:
        return self.get_by_test_id(ElementIDs.CONTEXT_SUMMARY)

    def get_queued_message_card(self) -> Locator:
        return self.get_by_test_id(ElementIDs.QUEUED_MESSAGE_CARD)

    def get_delete_queued_message_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DELETE_QUEUED_MESSAGE_BUTTON)

    def get_messages(self) -> Locator:
        all_messages = self.get_by_test_id(ElementIDs.CHAT_PANEL_MESSAGE)

        # Filter for assistant or user messages to avoid snapshot messages. May need changes in the future
        return all_messages.locator(
            f"[data-testid='{ElementIDs.ASSISTANT_MESSAGE}'], [data-testid='{ElementIDs.USER_MESSAGE}']"
        )

    def get_error_block(self) -> Locator:
        return self.get_by_test_id(ElementIDs.ERROR_BLOCK)

    def get_error_block_retry_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.ERROR_BLOCK_RETRY_BUTTON)

    def get_open_system_prompt_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.CHAT_PANEL_SYSTEM_PROMPT_OPEN_BUTTON)

    def get_system_prompt_text(self) -> Locator:
        return self.get_by_test_id(ElementIDs.CHAT_PANEL_SYSTEM_PROMPT_TEXT)

    def get_save_system_prompt_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.CHAT_PANEL_SYSTEM_PROMPT_SAVE_BUTTON)

    def get_feedback_buttons(self) -> PlaywrightFeedbackButtonsElement:
        feedback_buttons = self.get_by_test_id(ElementIDs.MESSAGE_ACTION_BAR)
        return PlaywrightFeedbackButtonsElement(locator=feedback_buttons, page=self._page)

    def get_feedback_dialog(self) -> PlaywrightFeedbackDialogElement:
        feedback_dialog = self._page.get_by_test_id(ElementIDs.FEEDBACK_DIALOG)
        return PlaywrightFeedbackDialogElement(locator=feedback_dialog, page=self._page)

    def open_feedback_dialog(self, thumbs_up_button: bool | None = True) -> Locator:
        """Open the Feedback Dialog."""
        if thumbs_up_button:
            self.get_feedback_buttons().get_thumbs_up_button().click()
        else:
            self.get_feedback_buttons().get_thumbs_down_button().click()
        dialog = PlaywrightFeedbackDialogElement(
            locator=self._page.get_by_test_id(ElementIDs.FEEDBACK_DIALOG), page=self._page
        )

        expect(dialog).to_be_visible()

        return dialog

    def get_model_selector(self) -> Locator:
        return self.get_by_test_id(ElementIDs.MODEL_SELECTOR)

    def get_model_options(self) -> Locator:
        """Get all model options in the dropdown."""
        return self._page.get_by_test_id(ElementIDs.MODEL_OPTION)

    def get_forked_to_block(self) -> Locator:
        """Get the forked to block (shown in parent task)."""
        return self.get_by_test_id(ElementIDs.FORKED_TO_BLOCK)

    def get_forked_from_block(self) -> Locator:
        """Get the forked from block (shown in child task)."""
        return self.get_by_test_id(ElementIDs.FORKED_FROM_BLOCK)


def expect_message_to_have_role(message: Locator, role: ElementIDs) -> None:
    expect(message).to_have_attribute("data-testid", role)


def wait_for_completed_message_count(chat_panel, expected_message_count: int) -> None:
    """Wait for assistant to finish responding."""
    expect(chat_panel.get_messages()).to_have_count(expected_message_count)
    expect(chat_panel).to_have_attribute("data-is-streaming", "false")


def send_chat_message(chat_panel, message: str) -> None:
    """Send a message in chat and verify input is cleared."""
    chat_input = chat_panel.get_chat_input()
    chat_input.type(message)
    chat_panel.get_send_button().click()
    expect(chat_input).to_have_text("")


def select_model_by_name(chat_panel: PlaywrightChatPanelElement, model_name: str) -> str:
    """Select a model by its exact name from the model selector dropdown and return the selected text.

    Args:
        chat_panel: The chat panel element
        model_name: The exact name of the model to select

    Returns:
        The text shown in the selector after selection
    """
    model_selector = chat_panel.get_model_selector()
    # Open the dropdown
    model_selector.click()

    # Get all options and find the one with exact matching text
    options = chat_panel.get_model_options()

    # Check each option for exact match
    target_model_option = only([option for option in options.all() if option.inner_text().strip() == model_name])
    target_model_option.click()

    return model_selector.inner_text()
