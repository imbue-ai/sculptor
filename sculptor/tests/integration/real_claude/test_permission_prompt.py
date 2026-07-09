"""Real Claude integration tests: permission prompt handling for .claude/ writes.

Verifies that the agent can write to files under the .claude/ directory (skills,
settings, etc.) which Claude Code protects with permission prompts even when
--dangerously-skip-permissions is used.

The fix requires:
1. --permission-prompt-tool stdio so the CLI sends permission requests via the
   stdin control protocol instead of blocking for interactive prompts.
2. The output processor auto-approving can_use_tool control_request messages.
"""

import pytest

from sculptor.testing.sculptor_instance import SculptorInstance
from tests.integration.real_claude.helpers import assert_has_completed_tool_calls
from tests.integration.real_claude.helpers import assert_last_message_contains
from tests.integration.real_claude.helpers import assert_no_errors
from tests.integration.real_claude.helpers import create_workspace_and_send
from tests.integration.real_claude.helpers import real_claude
from tests.integration.real_claude.helpers import send_and_wait

_WRITE_PROMPT = (
    "Do these steps in order:\n"
    + "1. Use the Write tool to create a file at the path '.claude/skills/test-permission-sentinel/SKILL.md' "
    + "with this exact content:\n"
    + "---\nname: test-permission-sentinel\ndescription: PERMISSION-SENTINEL-82941\n---\n\n"
    + "2. Then use the Read tool to read back '.claude/skills/test-permission-sentinel/SKILL.md' "
    + "and confirm the content.\n"
    + "3. Reply with exactly: PERMISSION-WRITE-DONE-82941"
)

_VERIFY_PROMPT = (
    "Use the Bash tool to run: cat .claude/skills/test-permission-sentinel/SKILL.md. "
    + "Then tell me the content, starting with FILE-CONTENT:"
)

# The fresh initial_repo the fixture creates has no '.claude/README.md', so the
# prompt seeds it with the Write tool first (like _WRITE_PROMPT does), then
# exercises the Edit tool on that existing '.claude/' file. Reading a
# non-existent file would error, and an errored tool call renders as
# data-tool-state='error' (not 'completed'), so assert_has_completed_tool_calls
# would never be satisfied.
_EDIT_PROMPT = (
    "Do these steps in order:\n"
    + "1. First use the Write tool to create the file '.claude/README.md'. Its content must be "
    + "EXACTLY the text between the two markers below, and must NOT include the markers themselves "
    + "or any of the step text:\n"
    + "-----BEGIN FILE CONTENT-----\n"
    + "# Test README\n\nInitial content line.\n"
    + "-----END FILE CONTENT-----\n"
    + "2. Then use the Edit tool on '.claude/README.md' to append the line "
    + "'<!-- EDIT-SENTINEL-37502 -->' at the end of the file, keeping the existing content.\n"
    + "3. Then use the Read tool to read '.claude/README.md' again and confirm both the initial "
    + "content and the appended comment are present.\n"
    + "4. Reply with exactly: EDIT-DONE-37502"
)

_EDIT_VERIFY_PROMPT = (
    "Use the Bash tool to run: cat .claude/README.md. Then tell me if it contains 'EDIT-SENTINEL-37502'. "
    + "Reply with exactly EDIT-VERIFIED if it does, or EDIT-MISSING if it doesn't."
)


@real_claude
@pytest.mark.timeout(300)
def test_write_to_claude_skill_file(sculptor_instance_: SculptorInstance) -> None:
    """Verify the agent can edit an existing file under .claude/skills/.

    Claude Code protects .claude/ files with permission prompts even when
    --dangerously-skip-permissions is set. Without --permission-prompt-tool stdio
    and auto-approval of can_use_tool control requests, this write fails silently.
    """
    # We use a unique sentinel so we can verify the exact content was written.
    task_page = create_workspace_and_send(sculptor_instance_, _WRITE_PROMPT)
    chat_panel = task_page.get_chat_panel()
    assert_has_completed_tool_calls(chat_panel)
    assert_last_message_contains(chat_panel, "PERMISSION-WRITE-DONE-82941")
    assert_no_errors(chat_panel)

    # Step 2: Independently verify the file was written by reading it with Bash
    send_and_wait(chat_panel, _VERIFY_PROMPT)
    assert_last_message_contains(chat_panel, "PERMISSION-SENTINEL-82941")


@real_claude
@pytest.mark.timeout(300)
def test_edit_existing_claude_file(sculptor_instance_: SculptorInstance) -> None:
    """Verify the agent can edit an existing file under .claude/ using the Edit tool.

    This tests the Edit tool specifically, which may have different permission
    handling than the Write tool.
    """
    task_page = create_workspace_and_send(sculptor_instance_, _EDIT_PROMPT)
    chat_panel = task_page.get_chat_panel()
    assert_has_completed_tool_calls(chat_panel)
    assert_last_message_contains(chat_panel, "EDIT-DONE-37502")
    assert_no_errors(chat_panel)

    # Verify via Bash
    send_and_wait(chat_panel, _EDIT_VERIFY_PROMPT)
    assert_last_message_contains(chat_panel, "EDIT-VERIFIED")
