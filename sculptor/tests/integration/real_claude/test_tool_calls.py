"""Real Claude integration tests: tool calls.

Verifies that various tools (Write, Bash, Read) work correctly with the
stdin protocol.
"""

import pytest

from sculptor.testing.sculptor_instance import SculptorInstance
from tests.integration.real_claude.helpers import assert_has_completed_tool_calls
from tests.integration.real_claude.helpers import assert_last_message_contains
from tests.integration.real_claude.helpers import assert_no_errors
from tests.integration.real_claude.helpers import create_workspace_and_send
from tests.integration.real_claude.helpers import real_claude
from tests.integration.real_claude.helpers import send_and_wait


@real_claude
@pytest.mark.timeout(300)
def test_write_tool(sculptor_instance_: SculptorInstance) -> None:
    """Verify the Write tool works with the stdin protocol."""
    task_page = create_workspace_and_send(
        sculptor_instance_,
        (
            "Use the Write tool to create a file at the path 'stdin-test-write.txt' with the exact content 'WRITE-TOOL-SENTINEL-44920'. Then reply with exactly: WRITE-DONE."
        ),
    )
    chat_panel = task_page.get_chat_panel()
    assert_has_completed_tool_calls(chat_panel)
    assert_last_message_contains(chat_panel, "WRITE-DONE")
    assert_no_errors(chat_panel)

    # Verify the file was actually created by asking the agent to read it back
    send_and_wait(
        chat_panel,
        "Use the Bash tool to run: cat stdin-test-write.txt. Then tell me the content, starting with FILE-CONTENT:",
    )
    assert_last_message_contains(chat_panel, "WRITE-TOOL-SENTINEL-44920")


@real_claude
@pytest.mark.timeout(300)
def test_bash_tool(sculptor_instance_: SculptorInstance) -> None:
    """Verify the Bash tool works with the stdin protocol."""
    task_page = create_workspace_and_send(
        sculptor_instance_,
        (
            "Use the Bash tool to run exactly this command: echo 'BASH-SENTINEL-77301'. Then reply with exactly: BASH-DONE."
        ),
    )
    chat_panel = task_page.get_chat_panel()
    assert_has_completed_tool_calls(chat_panel)
    assert_last_message_contains(chat_panel, "BASH-DONE")
    assert_no_errors(chat_panel)


@real_claude
@pytest.mark.timeout(300)
def test_read_tool(sculptor_instance_: SculptorInstance) -> None:
    """Verify Read tool works (tests a tool that doesn't modify state)."""
    # First create a file for the agent to read
    task_page = create_workspace_and_send(
        sculptor_instance_,
        (
            "Use the Bash tool to run: echo 'READ-ME-SENTINEL-99201' > read-test-input.txt. Then reply with exactly: FILE-CREATED."
        ),
    )
    chat_panel = task_page.get_chat_panel()
    assert_last_message_contains(chat_panel, "FILE-CREATED")

    # Now ask the agent to read it
    send_and_wait(
        chat_panel,
        (
            "Use the Read tool to read the file 'read-test-input.txt'. Tell me what it contains. Reply in the format: FILE-CONTAINS: <content>"
        ),
    )
    assert_last_message_contains(chat_panel, "READ-ME-SENTINEL-99201")


@real_claude
@pytest.mark.timeout(300)
def test_sequential_tool_calls(sculptor_instance_: SculptorInstance) -> None:
    """Verify multi-step tool use works (agent loops: tool call → result → next)."""
    task_page = create_workspace_and_send(
        sculptor_instance_,
        (
            "Do these steps in order:\n1. Use Write to create 'step-a.txt' with content 'ALPHA-STEP'\n2. Use Bash to run: cat step-a.txt\n3. Reply with exactly: SEQUENCE-DONE-83012"
        ),
    )
    chat_panel = task_page.get_chat_panel()
    assert_last_message_contains(chat_panel, "SEQUENCE-DONE-83012")
    assert_no_errors(chat_panel)


@real_claude
@pytest.mark.timeout(300)
def test_parallel_tool_calls(sculptor_instance_: SculptorInstance) -> None:
    """Verify the agent can invoke multiple tools in a single turn."""
    task_page = create_workspace_and_send(
        sculptor_instance_,
        (
            "In a single response, do all of these at once (in parallel if possible):\n- Use Write to create 'parallel-a.txt' with content 'PARA-A'\n- Use Write to create 'parallel-b.txt' with content 'PARA-B'\nThen reply with exactly: PARALLEL-DONE-50821"
        ),
    )
    chat_panel = task_page.get_chat_panel()
    assert_last_message_contains(chat_panel, "PARALLEL-DONE-50821")
    assert_no_errors(chat_panel)
