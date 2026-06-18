"""Tests for the two distinct error behaviors in Sculptor.

Covers:
1. Request-level errors (e.g. API 429) — error block in chat, agent stays running
2. Unrecoverable crashes — error block in chat, task enters ERROR state
3. API error fires while user is on another workspace — peek shows error,
   returning to the workspace clears it to gray
4. Crash fires while user is on another workspace — peek shows error,
   returning to the workspace keeps it red
"""

from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.playwright_utils import navigate_to_home_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# How long (seconds) FakeClaude waits before firing the error.  Must be long
# enough for the test to navigate away from the workspace first.
_ERROR_DELAY_SECONDS = 5


# ---------------------------------------------------------------------------
# 1. Request-level error (API error) — agent stays running
# ---------------------------------------------------------------------------


@user_story("to see an error block when the API returns a transient error, but continue using the agent")
def test_api_error_shows_error_block_and_agent_stays_running(sculptor_instance_: SculptorInstance) -> None:
    """When the Claude CLI reports an API error (e.g. 429 rate limit), the UI
    should show an error block in the chat but the agent should remain in a
    usable state — not enter the ERROR state that requires a restore."""
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt='fake_claude:api_error `{"message": "API Error: 429 Rate limited"}`',
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Wait for the agent turn to finish (error is processed, thinking stops).
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()

    # An error block should be visible in the chat.
    expect(chat_panel.get_error_block()).to_be_visible()

    # The agent should NOT be in error state — verify by sending a follow-up
    # message and confirming it completes successfully.
    send_chat_message(chat_panel, 'fake_claude:text `{"text": "Recovery after API error"}`')
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()
    expect(chat_panel.get_messages().last).to_contain_text("Recovery after API error")


# ---------------------------------------------------------------------------
# 1b. Usage limit reached — thinking indicator must clear, agent stays running
# ---------------------------------------------------------------------------


@user_story("to have the thinking indicator clear (not spin forever) when the account usage limit is reached")
def test_usage_limit_clears_thinking_indicator_and_shows_error(sculptor_instance_: SculptorInstance) -> None:
    """When the Claude CLI reports the account usage limit was reached — a
    ``rate_limit_event`` with ``status="rejected"`` — and then pauses without
    emitting a terminating ``result`` message, the "Thinking..." indicator must
    not spin forever (SCU-1129).

    The rate_limit_event frame carries no end-of-turn signal, so without
    handling it the output loop waits indefinitely and the task stays RUNNING.
    Sculptor should instead surface an error block and settle the agent into a
    usable state, exactly like a transient API error."""
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt="fake_claude:usage_limit `{}`",
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # The turn starts and the agent shows the "Thinking..." indicator.
    expect(chat_panel.get_thinking_indicator()).to_be_visible()

    # The indicator must then clear even though the CLI never sent a terminating
    # result and the fake process is still alive (paused on the usage limit).
    # Before the fix it spins forever — this is the core SCU-1129 symptom.
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()

    # An error block should explain that the usage limit was reached.
    expect(chat_panel.get_error_block()).to_be_visible()

    # The agent should NOT be wedged — sending a follow-up message completes
    # successfully, proving the usage limit settled into a recoverable state.
    send_chat_message(chat_panel, 'fake_claude:text `{"text": "Recovery after usage limit"}`')
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible()
    expect(chat_panel.get_messages().last).to_contain_text("Recovery after usage limit")


# ---------------------------------------------------------------------------
# 2. Unrecoverable crash — task enters ERROR state
# ---------------------------------------------------------------------------


@user_story("to see the task enter error state when the agent crashes unrecoverably")
def test_crash_puts_task_in_error_state(sculptor_instance_: SculptorInstance) -> None:
    """When the agent encounters an unrecoverable internal error (not an
    AgentClientError), the task should enter the ERROR state.  The UI should
    show an error block and the 'restore agent' prompt — the user cannot send
    new messages until the agent is restored."""
    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt="fake_claude:crash `{}`",
        wait_for_agent_to_finish=False,
    )

    # The ErrorInput component should appear (renders only when
    # taskStatus === TaskStatus.ERROR).  This is the distinctive marker of the
    # ERROR state — the chat input is replaced with a restore link, preventing
    # new messages until the agent is restored.
    expect(task_page.get_error_input()).to_be_visible()


# ---------------------------------------------------------------------------
# 3. API error fires while user is on another workspace
# ---------------------------------------------------------------------------


@user_story("to notice an API error from another workspace and see it clear when returning")
def test_api_error_shows_error_in_workspace_peek_and_clears_on_return(
    sculptor_instance_: SculptorInstance,
) -> None:
    """When the agent hits a request-level API error while the user is on a
    different workspace, the peek popover should show an error banner.  After
    navigating back, the agent tab dot should revert to read (gray) — the
    error is acknowledged by viewing the workspace."""
    page = sculptor_instance_.page

    # Step 1: Start an agent that will error after a delay, giving us time
    # to navigate away before the error fires.
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:api_error `{{"message": "API Error: 429 Rate limited", "delay_seconds": {_ERROR_DELAY_SECONDS}}}`',
        workspace_name="API Error WS",
        wait_for_agent_to_finish=False,
    )

    # Step 2: Navigate away before the error fires.
    navigate_to_home_page(page)

    # Step 3: Hover the workspace tab to open the peek popover.  Use a
    # timeout that accounts for the delay — the error hasn't fired yet.
    workspace_tab = task_page.get_workspace_tabs().first
    workspace_tab.hover()

    workspace_peek = task_page.get_workspace_peek_popover()
    expect(workspace_peek).to_be_visible()

    # Wait for the peek banner to show the error (appears after the delay).
    banner = workspace_peek.get_banner()
    expect(banner).to_contain_text("error")

    # Step 4: Navigate back to the workspace by clicking the tab.
    page.mouse.move(0, 0)  # Dismiss the popover first.
    workspace_tab.click()

    # The agent tab dot should revert to read (gray) — the error is
    # acknowledged by viewing the workspace.
    agent_tab = task_page.get_agent_tab_bar().get_agent_tabs().first
    expect(agent_tab).to_have_attribute("data-dot-status", "read")


# ---------------------------------------------------------------------------
# 4. Crash fires while user is on another workspace
# ---------------------------------------------------------------------------


@user_story("to notice an agent crash from another workspace and see it persist when returning")
def test_crash_shows_error_in_workspace_peek_and_persists_on_return(
    sculptor_instance_: SculptorInstance,
) -> None:
    """When the agent crashes while the user is on a different workspace, the
    peek popover should show an error banner.  Unlike a transient API error,
    navigating back should NOT clear the red dot — the task is in ERROR state
    and requires an explicit restore."""
    page = sculptor_instance_.page

    # Step 1: Start an agent that will crash after a delay, giving us time
    # to navigate away before the crash fires.
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f'fake_claude:crash `{{"delay_seconds": {_ERROR_DELAY_SECONDS}}}`',
        workspace_name="Crash WS",
        wait_for_agent_to_finish=False,
    )

    # Step 2: Navigate away before the crash fires.
    navigate_to_home_page(page)

    # Step 3: Hover the workspace tab to open the peek popover.
    workspace_tab = task_page.get_workspace_tabs().first
    workspace_tab.hover()

    workspace_peek = task_page.get_workspace_peek_popover()
    expect(workspace_peek).to_be_visible()

    # Wait for the peek banner to show the error (appears after the delay).
    banner = workspace_peek.get_banner()
    expect(banner).to_contain_text("error")

    # Step 4: Navigate back to the workspace by clicking the tab.
    page.mouse.move(0, 0)  # Dismiss the popover first.
    workspace_tab.click()

    # The agent tab dot should STILL be red — the crash requires an explicit
    # restore, not just viewing the workspace.
    agent_tab = task_page.get_agent_tab_bar().get_agent_tabs().first
    expect(agent_tab).to_have_attribute("data-dot-status", "error")
