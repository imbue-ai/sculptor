"""Integration tests for plan mode.

Tests cover seven areas:
- Group A: Agent-initiated plan mode (EnterPlanMode lights up plan toggle)
- Group B: ExitPlanMode approval flow (approve, revise, dismiss, page reload)
- Group C: User-initiated plan mode ("Plan first" toggle in ChatInput)
- Group D: Write + ExitPlanMode in same message (tool grouping isolation)
- Group E: Open plan file in document viewer from chat panel
- Group F: Auto-open and clicking ExitPlanMode block opens plan file in document viewer
- Group G: AskUserQuestion during plan mode
"""

from playwright.sync_api import expect

from sculptor.testing.elements.ask_user_question import get_ask_user_question_panel
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.playwright_utils import navigate_away_and_back
from sculptor.testing.playwright_utils import soft_reload_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

PLAN_MODE_MULTI_STEP_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {"command": "enter_plan_mode"},
    {"command": "text", "args": {"text": "Here is my plan: I will implement feature X by modifying files A, B, and C."}},
    {"command": "exit_plan_mode"}
  ]
}`"""


@user_story("to see the plan toggle light up when the agent enters plan mode")
def test_plan_toggle_lights_up_on_enter_plan_mode(sculptor_instance_: SculptorInstance) -> None:
    """Test that calling EnterPlanMode lights up the plan-first toggle in the chat input.

    Uses a solo enter_plan_mode command (no exit) so isInPlanMode stays true
    after the agent finishes. The multi_step variant processes too fast for
    the state to be observed between enter and exit.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="fake_claude:enter_plan_mode",
        wait_for_agent_to_finish=True,
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # The plan-first toggle should light up since we entered plan mode but never exited
    toggle = chat_panel.get_plan_mode_toggle()
    expect(toggle).to_have_attribute("data-active", "true")


@user_story("to NOT see a 'needs your approval' workspace peek banner just because the agent entered plan mode")
def test_enter_plan_mode_does_not_trigger_waiting_status(sculptor_instance_: SculptorInstance) -> None:
    """Regression test: EnterPlanMode alone must NOT mark the agent as WAITING.

    The yellow peek banner and "Waiting for plan approval" detail are reserved
    for ExitPlanMode (the agent has presented a plan and is awaiting user
    approval). Calling EnterPlanMode (the agent has begun planning internally)
    must leave the workspace status idle/working, since there is nothing for
    the user to act on yet.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="fake_claude:enter_plan_mode",
        workspace_name="EnterPlanMode WS",
        wait_for_agent_to_finish=True,
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Sanity: the plan-first toggle is lit (so is_in_plan_mode is True).
    toggle = chat_panel.get_plan_mode_toggle()
    expect(toggle).to_have_attribute("data-active", "true")

    # Hover the workspace's sidebar row to trigger the peek popover.
    get_workspace_sidebar(page).get_workspace_rows().first.hover()

    peek = task_page.get_workspace_peek_popover()
    expect(peek).to_be_visible()

    # The waiting banner must NOT be visible — EnterPlanMode alone is not
    # a "needs your input/approval" signal. ExitPlanMode is what triggers
    # the waiting state, and it has not been called.
    banner = peek.get_banner()
    expect(banner).to_be_hidden()


@user_story("to see the plan toggle turn off when the plan is ready")
def test_plan_toggle_clears_on_plan_approval(sculptor_instance_: SculptorInstance) -> None:
    """Test that the plan-first toggle stops being lit once the plan is approved.

    Plan mode is only truly cleared when the user approves the plan — revision
    and dismissal both keep the agent in plan mode. The ChatInput (which
    contains the toggle) and AskUserQuestion are mutually exclusive — when the
    approval prompt is visible, the toggle is not in the DOM — so we approve
    the plan first, then verify the toggle is no longer lit.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=PLAN_MODE_MULTI_STEP_PROMPT,
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Wait for the approval prompt, then approve
    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel).to_be_visible()
    auq_panel.select_option("Approve plan")
    auq_panel.submit()

    expect(auq_panel).not_to_be_visible()

    # The plan-first toggle should no longer be lit (approval clears is_in_plan_mode)
    toggle = chat_panel.get_plan_mode_toggle()
    expect(toggle).to_be_visible()
    expect(toggle).to_have_attribute("data-active", "false")


@user_story("to see the EnterPlanMode tool block in the chat")
def test_enter_plan_mode_tool_block_renders_in_chat(sculptor_instance_: SculptorInstance) -> None:
    """Test that the EnterPlanMode tool block appears in the chat with a display name.

    EnterPlanMode emits a tool_use block (without a matching tool_result in
    FakeClaude), so the frontend renders it with the present-tense name from
    getToolDisplayNamePresent().
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt="fake_claude:enter_plan_mode",
        wait_for_agent_to_finish=True,
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # EnterPlanMode renders as an alpha tool line with the raw tool name.
    tool_names = chat_panel.get_tool_names().filter(has_text="EnterPlanMode")
    expect(tool_names.first).to_be_visible()


# Prompt that puts EnterPlanMode alongside other tools in the same message.
# EnterPlanMode should render at the top level, not hidden in "Called Tools".
ENTER_PLAN_MODE_WITH_OTHER_TOOLS_PROMPT = """\
fake_claude:parallel_tools `{
  "tools": [
    {"tool_name": "Write", "tool_input": {"file_path": "README.md", "content": "# README"}},
    {"tool_name": "EnterPlanMode", "tool_input": {}}
  ]
}`"""


@user_story("to see the EnterPlanMode tool block at the top level when grouped with other tools")
def test_enter_plan_mode_not_hidden_in_collapsed_called_tools(sculptor_instance_: SculptorInstance) -> None:
    """Regression test: EnterPlanMode must be visible at the top level.

    When EnterPlanMode is in the same message as other tools (e.g. Write),
    it should NOT be hidden inside a collapsed "Called Tools" group.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=ENTER_PLAN_MODE_WITH_OTHER_TOOLS_PROMPT,
        wait_for_agent_to_finish=True,
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # The EnterPlanMode tool should be visible at the top level. Alpha routes
    # EnterPlanMode through topLevelBlocks so it renders as a standalone
    # ALPHA_CHAT_TOOL_LINE — not collapsed into a parallel-tools pill row.
    tool_names = chat_panel.get_tool_names().filter(has_text="EnterPlanMode")
    expect(tool_names.first).to_be_visible()


@user_story("to approve a plan proposed by the agent")
def test_exit_plan_mode_shows_approval_prompt(sculptor_instance_: SculptorInstance) -> None:
    """Test the full ExitPlanMode -> approval prompt -> approve flow."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=PLAN_MODE_MULTI_STEP_PROMPT,
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel).to_be_visible()

    question_text = auq_panel.get_question_text()
    expect(question_text).to_contain_text("How would you like to proceed")

    options = auq_panel.get_options()
    expect(options.filter(has_text="Approve plan").first).to_be_visible()
    revise_option = auq_panel.get_other_option()
    expect(revise_option).to_contain_text("Revise")

    auq_panel.select_option("Approve plan")
    auq_panel.submit()

    expect(auq_panel).not_to_be_visible()

    expect(chat_panel.get_thinking_indicator(), "agent to finish").not_to_be_visible()

    exit_plan_block = chat_panel.get_exit_plan_mode_block()
    expect(exit_plan_block).to_be_visible()
    expect(exit_plan_block).to_contain_text("Plan approved")
    expect(exit_plan_block).to_contain_text("Approved")


@user_story("to request revisions to a plan proposed by the agent")
def test_exit_plan_mode_revision_flow(sculptor_instance_: SculptorInstance) -> None:
    """Test the rejection/revision flow with custom feedback."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=PLAN_MODE_MULTI_STEP_PROMPT,
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel).to_be_visible()

    # Select the "Revise" option (the "other" slot, relabeled for plan approval)
    auq_panel.get_other_option().click()

    auq_panel.type_other_text("Please also consider edge cases")

    auq_panel.submit()

    expect(auq_panel).not_to_be_visible()

    expect(chat_panel.get_thinking_indicator(), "agent to finish").not_to_be_visible()

    exit_plan_block = chat_panel.get_exit_plan_mode_block()
    expect(exit_plan_block).to_be_visible()
    expect(exit_plan_block).to_contain_text("Plan revision requested")
    expect(exit_plan_block).to_contain_text("Revision")

    # The plan-first toggle must remain lit across the revision: the agent is
    # still in plan mode (user asked to revise, not approve), so the chat-input
    # toggle should reflect that.
    toggle = chat_panel.get_plan_mode_toggle()
    expect(toggle).to_be_visible()
    expect(toggle).to_have_attribute("data-active", "true")


@user_story("to see plan revision feedback expanded after submitting it")
def test_exit_plan_mode_revision_auto_expands(sculptor_instance_: SculptorInstance) -> None:
    """Regression test: the revision feedback should be auto-expanded after submission.

    When the user requests revisions to a plan, the ExitPlanMode tool block should
    automatically expand to show the feedback text, so the user can read their
    own answer without an extra click.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=PLAN_MODE_MULTI_STEP_PROMPT,
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel).to_be_visible()

    auq_panel.get_other_option().click()
    auq_panel.type_other_text("Please also handle error cases")
    auq_panel.submit()

    expect(auq_panel).not_to_be_visible()

    # The revision feedback should be visible without clicking to expand
    exit_plan_block = chat_panel.get_exit_plan_mode_block()
    expect(exit_plan_block).to_be_visible()
    expect(exit_plan_block).to_contain_text("Please also handle error cases")


@user_story("to preserve revision feedback when navigating away and back")
def test_exit_plan_mode_revision_preserves_text_after_navigation(sculptor_instance_: SculptorInstance) -> None:
    """Regression test: typed revision feedback survives navigating away and back.

    When the user selects "Revise" and types feedback text in the ExitPlanMode
    approval prompt, then navigates to the Open Workspace page and returns,
    the "Revise" selection and typed text must be preserved.
    """
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=PLAN_MODE_MULTI_STEP_PROMPT,
        wait_for_agent_to_finish=False,
    )

    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel).to_be_visible()

    auq_panel.get_other_option().click()
    auq_panel.type_other_text("Add better error handling")

    submit_button = auq_panel.get_submit_button()
    expect(submit_button).to_be_enabled()

    navigate_away_and_back(page)

    # The approval prompt should reappear with state preserved
    expect(auq_panel).to_be_visible()

    other_input = auq_panel.get_other_input()
    expect(other_input).to_be_visible()
    expect(other_input).to_have_value("Add better error handling")

    expect(submit_button).to_be_enabled()


@user_story("to dismiss a plan review without answering")
def test_exit_plan_mode_dismiss_flow(sculptor_instance_: SculptorInstance) -> None:
    """Test dismissing the approval prompt."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=PLAN_MODE_MULTI_STEP_PROMPT,
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel).to_be_visible()

    auq_panel.dismiss()

    expect(auq_panel).not_to_be_visible()

    expect(chat_panel.get_thinking_indicator(), "agent to finish").not_to_be_visible()

    # Verify the most recent ExitPlanMode tool block shows dismissed state.
    # Use .last because a prior agent session in the shared instance may have
    # left an earlier EXIT_PLAN_MODE_TOOL_BLOCK in the DOM.
    exit_plan_block = chat_panel.get_exit_plan_mode_block().last
    expect(exit_plan_block).to_be_visible()
    expect(exit_plan_block).to_contain_text("Plan review dismissed")
    expect(exit_plan_block).to_contain_text("Dismissed")


@user_story("to see a plan review prompt survive page reload")
def test_exit_plan_mode_survives_page_reload(sculptor_instance_: SculptorInstance) -> None:
    """Test that the pending approval prompt is reconstructed after page reload."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=PLAN_MODE_MULTI_STEP_PROMPT,
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel).to_be_visible()

    soft_reload_page(page)

    # Approval prompt should re-appear after reload
    expect(auq_panel).to_be_visible()

    exit_plan_block = chat_panel.get_exit_plan_mode_block()
    expect(exit_plan_block).to_be_visible()

    auq_panel.select_option("Approve plan")
    auq_panel.submit()

    expect(auq_panel).not_to_be_visible()
    expect(chat_panel.get_thinking_indicator(), "agent to finish").not_to_be_visible()


@user_story("to see a plan-first toggle button in the chat input")
def test_plan_first_toggle_is_visible(sculptor_instance_: SculptorInstance) -> None:
    """Test that the 'Plan first' toggle button exists in the ChatInput toolbar."""
    page = sculptor_instance_.page

    # Start a task with a simple text command so ChatInput is visible
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:text `{"text": "Hello, world!"}`',
        wait_for_agent_to_finish=True,
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    toggle = chat_panel.get_plan_mode_toggle()
    expect(toggle).to_be_visible()


@user_story("to toggle the plan-first mode on and off")
def test_plan_first_toggle_activates_and_deactivates(sculptor_instance_: SculptorInstance) -> None:
    """Test that the toggle changes visual state on click."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:text `{"text": "Hello, world!"}`',
        wait_for_agent_to_finish=True,
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    toggle = chat_panel.get_plan_mode_toggle()

    expect(toggle).to_have_attribute("data-active", "false")

    toggle.click()

    expect(toggle).to_have_attribute("data-active", "true")

    toggle.click()

    expect(toggle).to_have_attribute("data-active", "false")


@user_story("to have the plan-first toggle persist after sending a message")
def test_plan_first_toggle_persists_after_send(sculptor_instance_: SculptorInstance) -> None:
    """Test that the toggle stays on after sending a message (persistent mode toggle)."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:text `{"text": "Hello, world!"}`',
        wait_for_agent_to_finish=True,
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    toggle = chat_panel.get_plan_mode_toggle()

    toggle.click()
    expect(toggle).to_have_attribute("data-active", "true")

    send_chat_message(chat_panel=chat_panel, message="Implement feature Y")

    # The toggle should remain on after send (persistent mode toggle)
    expect(toggle).to_have_attribute("data-active", "true")


WRITE_AND_EXIT_PLAN_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {"command": "enter_plan_mode"},
    {"command": "parallel_tools", "args": {"tools": [
      {"tool_name": "Write", "tool_input": {"file_path": "plan.md", "content": "# Plan\\nStep 1: Do X"}},
      {"tool_name": "ExitPlanMode", "tool_input": {"allowedPrompts": []}}
    ]}}
  ]
}`"""


@user_story("to see a completed Write tool block when Write and ExitPlanMode are in the same message")
def test_write_tool_shows_created_file_with_exit_plan_mode(sculptor_instance_: SculptorInstance) -> None:
    """Regression test: Write tool block must show 'Created file' (not 'Creating file...')
    when Write and ExitPlanMode are in the same assistant message.

    This reproduces the bug where the Write ToolUseBlock is never replaced by its
    ToolResultBlock when ExitPlanMode is in the same message, causing the UI to show
    the in-progress state ("Creating file...") instead of the completed state
    ("Created file").
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=WRITE_AND_EXIT_PLAN_PROMPT,
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Wait for the approval prompt (means ExitPlanMode was processed)
    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel).to_be_visible()

    # The Write tool should render as an alpha file chip — proof that its
    # ToolResultBlock arrived and the chip transitioned to the completed state
    # (the bug being guarded against would leave the chip stuck "Writing...").
    file_chip = chat_panel.get_file_chips()
    expect(file_chip.first).to_be_visible()

    # The ExitPlanMode block also renders inline as AlphaExitPlanModeBlock.
    exit_plan_block = chat_panel.get_exit_plan_mode_block()
    expect(exit_plan_block).to_be_visible()

    auq_panel.dismiss()
    expect(auq_panel).not_to_be_visible()

    # After dismissal, the Write file chip should still be visible.
    expect(file_chip.first).to_be_visible()


# Prompt with 3 parallel tools: a regular Write, a plan file Write, and
# ExitPlanMode. Uses the MCP-namespaced exit_plan_mode name (what real Claude
# emits) so the live output_processor handler fires, which is what publishes
# the OpenFileUiAction event for auto-open. ExitPlanMode gets isolated; the
# two Write results sit together in a "Called Tools" group. The user's
# entrypoint to the plan is the ExitPlanMode block.
WRITE_PLAN_FILE_WITH_OTHER_TOOLS_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {"command": "enter_plan_mode"},
    {"command": "parallel_tools", "args": {"tools": [
      {"tool_name": "Write", "tool_input": {"file_path": "README.md", "content": "# README"}},
      {"tool_name": "Write", "tool_input": {"file_path": ".claude/plans/plan.md", "content": "# Plan\\nStep 1: Do X"}},
      {"tool_name": "mcp__sculptor__exit_plan_mode", "tool_input": {"allowedPrompts": []}}
    ]}}
  ]
}`"""


@user_story("to see the ExitPlanMode block when the plan turn includes other tools")
def test_plan_file_write_with_other_tools_shows_exit_plan_mode_block(
    sculptor_instance_: SculptorInstance,
) -> None:
    """When ExitPlanMode fires in the same parallel batch as multiple Writes, the
    ExitPlanMode block — the user's entrypoint to the plan — must still render
    at the top level. The plan-file diff itself may now nest inside the
    collapsed "Called Tools" group; auto-open of the plan tab is driven by the
    backend OpenFileUiAction event (see Group F)."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=WRITE_PLAN_FILE_WITH_OTHER_TOOLS_PROMPT,
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Wait for the approval prompt (means ExitPlanMode was processed)
    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel).to_be_visible()

    # The ExitPlanMode block is the user's entrypoint to the plan — it must
    # be visible at the top level even when the parallel batch includes other
    # tool calls.
    exit_plan_block = chat_panel.get_exit_plan_mode_block()
    expect(exit_plan_block).to_be_visible()

    auq_panel.dismiss()
    expect(auq_panel).not_to_be_visible()


# Writes the plan file to .claude/plans/ in the same parallel batch as
# ExitPlanMode (mcp-namespaced — what real Claude emits, and what the live
# output_processor handler watches for). The output processor tracks the
# Write's path and publishes OpenFileUiAction(mode="file") when ExitPlanMode
# fires, which the frontend dispatcher routes into setActiveDiffTabAtom.
WRITE_PLAN_TO_PLANS_DIR_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {"command": "enter_plan_mode"},
    {"command": "parallel_tools", "args": {"tools": [
      {"tool_name": "Write", "tool_input": {"file_path": ".claude/plans/plan.md", "content": "# Plan\\nStep 1: Do X"}},
      {"tool_name": "mcp__sculptor__exit_plan_mode", "tool_input": {"allowedPrompts": []}}
    ]}}
  ]
}`"""


@user_story("to open a plan file in the document viewer from the chat panel")
def test_plan_file_opens_in_document_viewer(sculptor_instance_: SculptorInstance) -> None:
    """Plan-mode write of ``.claude/plans/...`` followed by the file chip's
    "View full diff" action must open a read-only *file view*, not a diff.

    This locks in the SCU-366 routing: ``AlphaChipDiffPopover`` detects plan
    files (path starts with ``.claude/plans/``) and routes them to
    ``openFileViewTab``, which renders the file as a read-only document.
    Accepting a diff view here would let a regression that reverted the
    routing slip through silently.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=WRITE_PLAN_TO_PLANS_DIR_PROMPT,
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Wait for the approval prompt (means ExitPlanMode was processed)
    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel).to_be_visible()

    # The Write tool should render as an alpha file chip for plan.md.
    file_chip = chat_panel.get_file_chips().filter(has_text="plan.md")
    expect(file_chip.first).to_be_visible()
    file_chip.first.click()

    popover = chat_panel.get_chip_popover()
    expect(popover).to_be_visible()
    chat_panel.get_chip_view_full_diff_button().click()

    # Plan files route to a read-only file view (READ_ONLY_PREVIEW) in the
    # single embedded viewer — not a diff view.
    task_page.get_diff_panel().expect_shows_file("plan.md")


@user_story("to see the plan file auto-open when the plan approval UI appears")
def test_plan_file_auto_opens_on_exit_plan_mode(sculptor_instance_: SculptorInstance) -> None:
    """Test that the plan file automatically opens in the document viewer when ExitPlanMode is pending.

    When the agent writes a plan file and calls ExitPlanMode, the plan file should
    open automatically in the document viewer without the user needing to click anything.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=WRITE_PLAN_TO_PLANS_DIR_PROMPT,
        wait_for_agent_to_finish=False,
    )

    # Wait for the approval prompt (means ExitPlanMode was processed)
    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel).to_be_visible()

    # The diff panel should automatically open with the plan file — no click needed
    task_page.get_diff_panel().expect_shows_file("plan.md")


@user_story("to open the plan file by clicking the ExitPlanMode block")
def test_exit_plan_mode_block_click_opens_plan_file(sculptor_instance_: SculptorInstance) -> None:
    """Test that clicking the 'Plan ready for review' block opens the plan file.

    When the agent writes a plan file and calls ExitPlanMode in the same message,
    clicking on the ExitPlanMode block should open the plan file in the document
    viewer panel.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=WRITE_PLAN_TO_PLANS_DIR_PROMPT,
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Wait for the approval prompt (means ExitPlanMode was processed)
    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel).to_be_visible()

    # The ExitPlanMode block should be visible with "Plan ready for review"
    exit_plan_block = chat_panel.get_exit_plan_mode_block()
    expect(exit_plan_block).to_be_visible()
    expect(exit_plan_block).to_contain_text("Plan ready for review")

    exit_plan_block.click()

    task_page.get_diff_panel().expect_shows_file("plan.md")


# Two write+exit cycles inside one fake_claude turn: V1, user approves, V2.
# The same plan-file path is rewritten with different content between the two
# ExitPlanMode calls. The file viewer must show V2 after the second
# ExitPlanMode — not the cached V1 content. Regression for SCU-471.
#
# Uses the sequential write_file + exit_plan_mode commands (not parallel_tools)
# because the inline-emitting exit_plan_mode blocks on the user's MCP response.
# That ordering guarantees the frontend has a chance to render V1 before the
# V2 write happens on disk.
PLAN_REWRITE_AND_REWRITE_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {"command": "enter_plan_mode"},
    {"command": "write_file", "args": {"file_path": ".claude/plans/plan.md", "content": "PLAN_TOKEN_VERSION_ONE"}},
    {"command": "exit_plan_mode"},
    {"command": "enter_plan_mode"},
    {"command": "write_file", "args": {"file_path": ".claude/plans/plan.md", "content": "PLAN_TOKEN_VERSION_TWO"}},
    {"command": "exit_plan_mode"}
  ]
}`"""


@user_story("to see the revised plan content after the agent rewrites the same plan file")
def test_plan_file_view_refreshes_when_rewritten(sculptor_instance_: SculptorInstance) -> None:
    """Regression test for SCU-471: the plan file viewer must refresh content when
    the same plan-file path is rewritten in a subsequent agent turn.

    The original bug was that ReadOnlyPreview fetched file content via a local
    useEffect keyed only on [workspaceId, filePath], so a same-path rewrite
    left the viewer stuck on the previous turn's content. SCU-513 replaced
    that with a TanStack Query keyed on (workspaceId, filePath, gitRef) that
    invalidates on the workspace's `diffUpdatedAt` WebSocket signal, which
    incidentally fixes this bug. This test guards against regression as the
    file-content fetch path evolves.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=PLAN_REWRITE_AND_REWRITE_PROMPT,
        wait_for_agent_to_finish=False,
    )

    # First ExitPlanMode: V1 written, approval prompt shown, viewer opens with V1.
    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel).to_be_visible()

    diff_panel = task_page.get_diff_panel()
    preview = diff_panel.get_read_only_preview()
    expect(preview).to_be_visible()
    expect(preview).to_contain_text("PLAN_TOKEN_VERSION_ONE")

    # Approve V1 — fake_claude's multi_step then continues to the second
    # write + exit_plan_mode pair, which rewrites the SAME plan-file path.
    auq_panel.select_option("Approve plan")
    auq_panel.submit()
    expect(auq_panel).not_to_be_visible()

    # Second ExitPlanMode: V2 has been written at the same path and the backend
    # publishes a fresh OpenFileUiAction. Wait for the new approval prompt as
    # the sync point for the second cycle.
    expect(auq_panel).to_be_visible()

    # The viewer must reflect the rewritten content — the same-path rewrite
    # must invalidate the cached previous content and refetch.
    expect(preview).to_contain_text("PLAN_TOKEN_VERSION_TWO")


ASK_DURING_PLAN_MODE_PROMPT = """\
fake_claude:enter_plan_mode_and_ask `{
  "questions": [
    {
      "question": "Which language should the plan use?",
      "header": "Language Choice",
      "options": [
        {"label": "Python", "description": "A versatile language"},
        {"label": "Go", "description": "For performance"}
      ],
      "multiSelect": false
    }
  ]
}`"""


@user_story("to answer a question the agent asks while in plan mode")
def test_ask_user_question_during_plan_mode(sculptor_instance_: SculptorInstance) -> None:
    """Test that AskUserQuestion works correctly when the agent is in plan mode.

    Reproduces a regression where the AUQ panel never appears because the
    process is killed before the streaming ContentBlockStopEvent for the
    AskUserQuestion tool is processed.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=ASK_DURING_PLAN_MODE_PROMPT,
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel).to_be_visible()

    question_text = auq_panel.get_question_text()
    expect(question_text).to_contain_text("Which language")

    auq_panel.get_options().first.click()
    auq_panel.submit()

    expect(auq_panel).not_to_be_visible()

    expect(chat_panel.get_thinking_indicator(), "agent to finish").not_to_be_visible()
