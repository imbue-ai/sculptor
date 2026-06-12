from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightAskUserQuestionPanelElement(PlaywrightIntegrationTestElement):
    def get_question_text(self) -> Locator:
        return self.get_by_test_id(ElementIDs.ASK_USER_QUESTION_TEXT)

    def get_options(self) -> Locator:
        return self.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OPTION)

    def get_other_option(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OTHER_OPTION)

    def get_other_input(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_OTHER_INPUT)

    def get_submit_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_SUBMIT)

    def get_dismiss_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_DISMISS_BUTTON)

    def select_first_option_and_submit(self) -> None:
        self.get_options().first.click()
        self.get_submit_button().click()

    def select_option_by_text(self, text: str) -> None:
        option = self.get_options().filter(has_text=text)
        option.first.click()

    def select_option(self, option_text: str) -> None:
        if option_text == "Other":
            self.get_other_option().click()
        else:
            option = self.get_options().filter(has_text=option_text)
            option.first.click()

    def type_other_text(self, text: str) -> None:
        self.get_other_input().fill(text)

    def submit(self) -> None:
        self.get_submit_button().click()

    def dismiss(self) -> None:
        self.get_dismiss_button().click()

    def navigate_next(self) -> None:
        self._page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_NEXT_BUTTON).click()

    def navigate_previous(self) -> None:
        self._page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_PREVIOUS_BUTTON).click()


class PlaywrightAskUserQuestionBlockElement(PlaywrightIntegrationTestElement):
    def get_custom_text(self) -> Locator:
        return self.get_by_test_id(ElementIDs.ASK_USER_QUESTION_CUSTOM_TEXT)

    def get_answered_options(self) -> Locator:
        return self.get_by_test_id(ElementIDs.ASK_USER_QUESTION_ANSWERED_OPTION)

    def get_question_text(self) -> Locator:
        return self.get_by_test_id(ElementIDs.ASK_USER_QUESTION_TEXT)

    def get_answer_text(self) -> Locator:
        return self.get_by_test_id(ElementIDs.ASK_USER_QUESTION_ANSWER_TEXT)

    def expect_question_visible(self, expected_question: str) -> None:
        question_elements = self.get_question_text()
        expect(question_elements.filter(has_text=expected_question).first).to_be_visible()

    def expect_answer_visible(self, expected_answer: str) -> None:
        answer_elements = self.get_answer_text()
        expect(answer_elements.filter(has_text=expected_answer).first).to_be_visible()

    def expect_answers_visible(self, expected_answers: list[str]) -> None:
        answer_elements = self.get_answer_text()
        for answer in expected_answers:
            expect(answer_elements.filter(has_text=answer).first).to_be_visible()

    def expect_submitted_state(self) -> None:
        expect(self._locator).not_to_contain_text("DISMISSED")

    def expect_dismissed_state(self) -> None:
        expect(self._locator).to_contain_text("DISMISSED")


def get_ask_user_question_panel(page: Page) -> PlaywrightAskUserQuestionPanelElement:
    locator = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_PANEL)
    return PlaywrightAskUserQuestionPanelElement(locator=locator, page=page)


def get_ask_user_question_block(page: Page) -> PlaywrightAskUserQuestionBlockElement:
    locator = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_TOOL_BLOCK)
    return PlaywrightAskUserQuestionBlockElement(locator=locator, page=page)


def get_first_ask_user_question_tool_block(page: Page) -> PlaywrightAskUserQuestionBlockElement:
    locator = page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_TOOL_BLOCK).first
    return PlaywrightAskUserQuestionBlockElement(locator=locator, page=page)


def get_ask_user_question_tool_blocks(page: Page) -> Locator:
    return page.get_by_test_id(ElementIDs.ASK_USER_QUESTION_TOOL_BLOCK)
