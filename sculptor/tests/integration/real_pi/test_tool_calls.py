"""Real pi integration tests: tool-call rendering.

Mirrors ``real_claude/test_tool_calls.py``. Drives a real ``pi --mode rpc``
subprocess against a real upstream model with prompts that force pi to use its
core tools (read / write / bash / edit), and asserts that the tool calls render
as completed tool blocks (name + result) and the turn succeeds — exercising the
pi-side tool-execution lane → Sculptor ToolUseBlock/ToolResultBlock adapter
end-to-end (``supports_tool_use_rendering``).

Divergence note (REQ-TEST-1 / REQ-CAP-ALL-3): Claude streams tool *input*
deltas as the call is generated; pi surfaces the complete input at
``tool_execution_start`` — equivalent fidelity, different rhythm. The rendered
result is the same completed tool block in both.
"""

import pytest
from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.sculptor_instance import SculptorInstance
from tests.integration.real_pi.helpers import RESPONSE_TIMEOUT_MS
from tests.integration.real_pi.helpers import create_pi_workspace_and_send
from tests.integration.real_pi.helpers import prefixed
from tests.integration.real_pi.helpers import real_pi


@real_pi
@pytest.mark.timeout(600)
def test_write_tool_renders_completed_block(sculptor_instance_: SculptorInstance) -> None:
    """A write tool call renders as a completed tool block and the turn succeeds."""
    prompt = (
        "Use your file-writing tool to create a file named 'pi-write-44920.txt' at the workspace root"
        + " with the exact contents 'PI-WRITE-SENTINEL-44920'. Then reply with exactly: WRITE-DONE-44920."
    )
    task_page = create_pi_workspace_and_send(sculptor_instance_, prompt)
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel.get_completed_tool_calls().first).to_be_visible(timeout=RESPONSE_TIMEOUT_MS)
    expect(chat_panel.get_in_progress_tool_calls()).to_have_count(0)
    expect(chat_panel.get_assistant_messages().last).to_contain_text("WRITE-DONE-44920")
    expect(chat_panel.get_error_block()).to_have_count(0)


@real_pi
@pytest.mark.timeout(600)
def test_bash_tool_renders_completed_block(sculptor_instance_: SculptorInstance) -> None:
    """A bash tool call renders as a completed tool block and the turn succeeds."""
    prompt = (
        "Use your shell tool to run exactly this command: echo 'PI-BASH-SENTINEL-77301'."
        + " Then reply with exactly: BASH-DONE-77301."
    )
    task_page = create_pi_workspace_and_send(sculptor_instance_, prompt)
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel.get_completed_tool_calls().first).to_be_visible(timeout=RESPONSE_TIMEOUT_MS)
    expect(chat_panel.get_in_progress_tool_calls()).to_have_count(0)
    expect(chat_panel.get_assistant_messages().last).to_contain_text("BASH-DONE-77301")
    expect(chat_panel.get_error_block()).to_have_count(0)


@real_pi
@pytest.mark.timeout(600)
def test_read_and_edit_tools_render_completed_blocks(sculptor_instance_: SculptorInstance) -> None:
    """Read then edit an existing file; both calls render as completed tool blocks.

    First turn creates a file (write/bash); a follow-up turn reads it and edits
    it, exercising the read and edit renderers (edit maps onto Claude's
    Edit/MultiEdit renderer). Each turn must surface completed tool blocks and
    no error.
    """
    create_prompt = (
        "Use your shell tool to run: echo 'READ-ME-SENTINEL-99201' > pi-read-99201.txt."
        + " Then reply with exactly: FILE-CREATED-99201."
    )
    task_page = create_pi_workspace_and_send(sculptor_instance_, create_prompt)
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel.get_assistant_messages().last).to_contain_text("FILE-CREATED-99201")
    expect(chat_panel.get_completed_tool_calls().first).to_be_visible(timeout=RESPONSE_TIMEOUT_MS)

    send_chat_message(
        chat_panel=chat_panel,
        message=prefixed(
            "Use your file-reading tool to read 'pi-read-99201.txt', then use your file-editing tool to"
            + " change 'READ-ME-SENTINEL-99201' to 'EDITED-SENTINEL-99201' in that file."
            + " Then reply with exactly: EDIT-DONE-99201."
        ),
    )
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4, timeout=RESPONSE_TIMEOUT_MS)
    expect(chat_panel.get_assistant_messages().last).to_contain_text("EDIT-DONE-99201")
    # Across both turns multiple tool calls completed (create, read, edit); the
    # follow-up turn left none stuck in-progress.
    expect(chat_panel.get_in_progress_tool_calls()).to_have_count(0)
    expect(chat_panel.get_error_block()).to_have_count(0)
