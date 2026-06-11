from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement
from sculptor.testing.elements.base import type_into_tiptap
from sculptor.testing.elements.file_preview_and_upload import PlaywrightFilePreviewAndUploadMixin


class PlaywrightChatPanelElement(PlaywrightFilePreviewAndUploadMixin, PlaywrightIntegrationTestElement):
    def get_chat_input(self) -> Locator:
        return self.get_by_test_id(ElementIDs.CHAT_INPUT)

    def get_send_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.SEND_BUTTON)

    def get_stop_button(self) -> Locator:
        """Returns the in-pill Stop IconButton, which appears only while the agent is cancellable."""
        return self.get_by_test_id(ElementIDs.STATUS_PILL_STOP)

    def get_status_pill(self) -> Locator:
        """Returns the status pill container in any lifecycle state.

        Use this when callers care about presence/absence of the pill itself
        (e.g. waiting for it to appear after a turn starts, or to disappear
        after a Stop click). For "agent is busy" filtering use
        ``get_thinking_indicator`` instead.

        Tests that want to read the current lifecycle phase should assert on
        the ``data-agent-state`` attribute on this element (e.g.
        ``expect(pill).to_have_attribute("data-agent-state", "waiting_for_background")``)
        rather than going through the label, which can lag the underlying
        state by the pill's debounce window.
        """
        return self.get_by_test_id(ElementIDs.STATUS_PILL)

    def get_status_pill_label(self) -> Locator:
        """Returns the visible label text element of the status pill (e.g.
        ``"Thinking..."``, ``"Streaming..."``, ``"Waiting for background tasks..."``).
        """
        return self.get_by_test_id(ElementIDs.STATUS_PILL_LABEL)

    def get_completed_tool_calls(self) -> Locator:
        """All alpha tool calls whose tool result has arrived.

        Matches the three alpha tool surfaces — pill (``ALPHA_CHAT_TOOL_PILL``,
        non-Bash), bash block (``ALPHA_CHAT_BASH_BLOCK``), and file chip
        (``ALPHA_CHAT_FILE_CHIP`` for Write / Edit / MultiEdit) — when they
        carry ``data-tool-state='completed'``.
        """
        alpha_pill = f"[data-testid='{ElementIDs.ALPHA_CHAT_TOOL_PILL}'][data-tool-state='completed']"
        alpha_bash = f"[data-testid='{ElementIDs.ALPHA_CHAT_BASH_BLOCK}'][data-tool-state='completed']"
        alpha_file = f"[data-testid='{ElementIDs.ALPHA_CHAT_FILE_CHIP}'][data-tool-state='completed']"
        return self._locator.locator(", ".join((alpha_pill, alpha_bash, alpha_file)))

    def get_completed_file_chips(self) -> Locator:
        """Completed file chips (Write / Edit / MultiEdit), the file-mutating surface."""
        return self._locator.locator(f"[data-testid='{ElementIDs.ALPHA_CHAT_FILE_CHIP}'][data-tool-state='completed']")

    def get_in_progress_tool_calls(self) -> Locator:
        """All alpha tool calls that have started but not yet received their result.

        These are orphaned ``ToolUseBlock`` renderings that were never replaced
        by their ``ToolResultBlock``. After streaming completes this should be
        empty.
        """
        alpha_pill = f"[data-testid='{ElementIDs.ALPHA_CHAT_TOOL_PILL}'][data-tool-state='initializing']"
        alpha_bash = f"[data-testid='{ElementIDs.ALPHA_CHAT_BASH_BLOCK}'][data-tool-state='initializing']"
        alpha_file = f"[data-testid='{ElementIDs.ALPHA_CHAT_FILE_CHIP}'][data-tool-state='initializing']"
        return self._locator.locator(", ".join((alpha_pill, alpha_bash, alpha_file)))

    def get_bash_blocks(self) -> Locator:
        return self.get_by_test_id(ElementIDs.ALPHA_CHAT_BASH_BLOCK)

    def get_bash_output(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.ALPHA_CHAT_BASH_OUTPUT)

    def get_context_summary_messages(self) -> Locator:
        return self.get_by_test_id(ElementIDs.CONTEXT_SUMMARY)

    def get_queued_message_bar(self) -> Locator:
        return self.get_by_test_id(ElementIDs.QUEUED_MESSAGE_BAR)

    def get_delete_queued_message_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.DELETE_QUEUED_MESSAGE_BUTTON)

    def get_queued_message_send_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.QUEUED_MESSAGE_SEND_BUTTON)

    def get_queued_message_edit_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.QUEUED_MESSAGE_EDIT_BUTTON)

    def get_queued_message_cancel_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.QUEUED_MESSAGE_CANCEL_BUTTON)

    def get_undo_queued_message_dialog(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.UNDO_QUEUED_MESSAGE_DIALOG)

    def get_undo_queued_message_cancel_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.UNDO_QUEUED_MESSAGE_CANCEL_BUTTON)

    def get_undo_queued_message_copy_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.UNDO_QUEUED_MESSAGE_COPY_BUTTON)

    def get_undo_queued_message_overwrite_button(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.UNDO_QUEUED_MESSAGE_OVERWRITE_BUTTON)

    def get_messages(self) -> Locator:
        """Get all message containers in the alpha chat view."""
        return self._locator.locator(f"[data-testid='{ElementIDs.ALPHA_CHAT_MESSAGE.value}']")

    def get_assistant_messages(self) -> Locator:
        """Get all assistant message containers in the alpha chat view."""
        return self._locator.locator(f"[data-testid='{ElementIDs.ALPHA_CHAT_MESSAGE.value}'][data-role='assistant']")

    def get_error_block(self) -> Locator:
        return self.get_by_test_id(ElementIDs.ERROR_BLOCK)

    def get_error_block_retry_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.ERROR_BLOCK_RETRY_BUTTON)

    def get_prompt_navigator_dots(self) -> Locator:
        return self.get_by_test_id(ElementIDs.PROMPT_NAVIGATOR_DOT)

    def get_prompt_navigator_up_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.PROMPT_NAVIGATOR_UP_BUTTON)

    def get_prompt_navigator_down_button(self) -> Locator:
        return self.get_by_test_id(ElementIDs.PROMPT_NAVIGATOR_DOWN_BUTTON)

    def get_prompt_navigator_collapsed_indicator(self) -> Locator:
        return self.get_by_test_id(ElementIDs.PROMPT_NAVIGATOR_COLLAPSED_INDICATOR)

    def get_thinking_indicator(self) -> Locator:
        """Match the status pill while the agent is in a non-final
        lifecycle phase (``thinking`` / ``streaming`` / ``calling_tools`` /
        ``compacting`` / ``stopping`` / ``waiting_for_background``).

        ``STATUS_PILL_STOP`` alone is too narrow — it only renders while
        the agent is cancellable, so a non-cancellable busy phase (e.g.
        post-stop cleanup) would read as idle. Filtering the pill by its
        ``data-agent-state`` covers every busy phase and resolves to no
        element once the state lands in ``idle`` / ``stopped``. Used by
        callers as the "agent is working" / "agent has settled" signal.

        ``waiting_for_background`` (SCU-387) is also busy — the turn isn't
        over until the in-flight background task delivers its
        ``task_notification``, so callers waiting for the agent to settle
        should still see the indicator during that window.
        """
        busy_states = (
            "thinking",
            "streaming",
            "calling_tools",
            "compacting",
            "stopping",
            "waiting_for_background",
        )
        selector = ", ".join(
            f'[data-testid="{ElementIDs.STATUS_PILL.value}"][data-agent-state="{state}"]' for state in busy_states
        )
        return self._locator.locator(selector)

    def get_status_pill_elapsed(self) -> Locator:
        return self.get_by_test_id(ElementIDs.STATUS_PILL_ELAPSED)

    def wait_for_agent_progress(self, min_advance_seconds: float = 1.0) -> None:
        """Wait until the status pill's elapsed timer advances by at least
        ``min_advance_seconds``.

        This is a virtualization-proof "the agent is still actively working and
        time has genuinely passed" signal — the status pill lives in the chat
        panel chrome, not the virtualized message list, so it stays mounted even
        when the streaming message has scrolled out of view. Use it to confirm a
        transient UI state persists across a span of continued agent activity
        without resorting to a fixed ``wait_for_timeout``. Requires the status
        pill to be visible (agent in a busy phase).
        """
        elapsed = self.get_status_pill_elapsed()
        expect(elapsed).to_be_visible()
        baseline = float((elapsed.text_content() or "0s").rstrip("s"))
        self._page.wait_for_function(
            f"""() => {{
                const el = document.querySelector('[data-testid="{ElementIDs.STATUS_PILL_ELAPSED.value}"]');
                return el !== null && parseFloat(el.textContent) >= {baseline + min_advance_seconds};
            }}""",
        )

    def get_status_pill_animation(self) -> Locator:
        return self.get_by_test_id(ElementIDs.STATUS_PILL_ANIMATION)

    def get_compacting_pill(self) -> Locator:
        """Locator that matches only when the alpha status pill is in the
        ``compacting`` lifecycle state. Pair with ``to_be_attached`` /
        ``not_to_be_attached`` so Playwright observes presence transitions
        rather than polling the attribute for a transient value.
        ``data-agent-state`` (not ``data-state``) is what the pill exposes;
        Radix HoverCard's own ``data-state`` injection would clobber a
        plain ``data-state``.
        """
        return self._locator.locator(f'[data-testid="{ElementIDs.STATUS_PILL.value}"][data-agent-state="compacting"]')

    def get_mention_list(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.MENTION_LIST)

    def get_mention_items(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.FILE_MENTION_SUGGESTION_ITEM)

    def get_mention_spans(self) -> Locator:
        return self.get_chat_input().get_by_test_id(ElementIDs.MENTION_SPAN)

    def get_entity_mention_chips(self) -> Locator:
        return self.get_chat_input().get_by_test_id(ElementIDs.ENTITY_MENTION_CHIP)

    def get_model_selector(self) -> Locator:
        return self.get_by_test_id(ElementIDs.MODEL_SELECTOR)

    def get_model_options(self) -> Locator:
        """Get all model options in the dropdown."""
        return self._page.get_by_test_id(ElementIDs.MODEL_OPTION)

    def get_fast_mode_toggle(self) -> Locator:
        return self.get_by_test_id(ElementIDs.FAST_MODE_TOGGLE)

    def get_plan_mode_toggle(self) -> Locator:
        return self.get_by_test_id(ElementIDs.PLAN_MODE_TOGGLE)

    def get_text_blocks(self) -> Locator:
        return self.get_by_test_id(ElementIDs.ALPHA_CHAT_TEXT)

    def get_tool_names(self) -> Locator:
        return self.get_by_test_id(ElementIDs.ALPHA_CHAT_TOOL_NAME)

    def get_exit_plan_mode_block(self) -> Locator:
        return self.get_by_test_id(ElementIDs.EXIT_PLAN_MODE_TOOL_BLOCK)

    def get_tool_pill_rows(self) -> Locator:
        return self.get_by_test_id(ElementIDs.ALPHA_CHAT_TOOL_PILL_ROW)

    def get_tool_pills(self) -> Locator:
        return self.get_by_test_id(ElementIDs.ALPHA_CHAT_TOOL_PILL)

    def get_tool_pill_popover(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.ALPHA_CHAT_TOOL_PILL_POPOVER)

    def get_subagent_pills(self) -> Locator:
        return self.get_by_test_id(ElementIDs.ALPHA_CHAT_SUBAGENT_PILL)

    def get_file_chips(self) -> Locator:
        return self.get_by_test_id(ElementIDs.ALPHA_CHAT_FILE_CHIP)

    def get_chip_popover(self) -> Locator:
        return self._page.get_by_test_id(ElementIDs.ALPHA_CHAT_CHIP_POPOVER)

    def get_chip_view_full_diff_button(self) -> Locator:
        return self.get_chip_popover().get_by_test_id(ElementIDs.ALPHA_CHAT_CHIP_VIEW_FULL_DIFF_BTN)

    def get_sent_via_badge(self, message: Locator) -> Locator:
        return message.get_by_test_id(ElementIDs.SCULPT_SENT_VIA_BADGE)

    def get_message_copy_button(self, message: Locator) -> Locator:
        return message.get_by_label("Copy message")

    def get_effort_selector(self) -> Locator:
        return self.get_by_test_id(ElementIDs.EFFORT_SELECTOR)

    def select_effort(self, text: str) -> None:
        self.get_effort_selector().click()
        options = self._page.get_by_test_id(ElementIDs.EFFORT_SELECTOR_OPTION)
        target = options.filter(has=self._page.get_by_text(text, exact=True))
        expect(target).to_be_visible()
        target.click()


def expect_message_to_have_role(message: Locator, role: ElementIDs) -> None:
    """Assert the alpha message has the expected role via data-role."""
    role_short = "user" if role == ElementIDs.USER_MESSAGE else "assistant"
    expect(message).to_have_attribute("data-role", role_short)


def wait_for_completed_message_count(
    chat_panel: PlaywrightChatPanelElement,
    expected_message_count: int,
    timeout: int | None = None,
) -> None:
    """Wait for assistant to finish responding.

    Args:
        timeout: Optional override for the Playwright expect timeout (ms).
            Useful for multi-step prompts that take longer under load.
    """
    kwargs = {"timeout": timeout} if timeout is not None else {}
    expect(chat_panel.get_queued_message_bar()).to_have_count(0, **kwargs)
    expect(chat_panel.get_messages()).to_have_count(expected_message_count, **kwargs)
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(**kwargs)


def send_chat_message(chat_panel, message: str) -> None:
    """Send a message in chat and verify input is cleared."""
    chat_input = chat_panel.get_chat_input()
    type_into_tiptap(chat_panel._page, chat_input, message)
    send_button = chat_panel.get_send_button()
    expect(send_button).to_be_enabled()
    send_button.click()
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

    # Wait for options to render, then find the exact match using Playwright's
    # locator filtering (auto-retries until the text appears, unlike a snapshot
    # via .all() which races on slower CI runners).  Use exact=True to avoid
    # substring matches (e.g. "Fake Claude" matching "Fake Claude 2").
    options = chat_panel.get_model_options()
    target_model_option = options.filter(has=chat_panel._page.get_by_text(model_name, exact=True))
    expect(target_model_option).to_be_visible()
    target_model_option.click()

    return model_selector.inner_text()
