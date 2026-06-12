"""Real Claude integration test: parallel slow bash + background task hang.

Reproduces a hang where a turn with parallel slow bash commands, a background
task, and a long-running foreground command causes the UI to get stuck in
"Streaming..." state after the turn completes.

The exact repro sequence that triggers the hang:
1. Three parallel bash sleeps (5s each)
2. A background bash sleep (10s, run_in_background=true)
3. A grep/search operation (fast)
4. A long-running foreground bash command (~10s)
5. Text output
"""

import pytest

from sculptor.testing.sculptor_instance import SculptorInstance
from tests.integration.real_claude.helpers import assert_any_message_contains
from tests.integration.real_claude.helpers import assert_no_errors
from tests.integration.real_claude.helpers import create_workspace_and_send
from tests.integration.real_claude.helpers import real_claude
from tests.integration.real_claude.helpers import wait_for_thinking_indicator_to_settle


@real_claude
@pytest.mark.timeout(300)
def test_parallel_slow_bash_with_background_task_completes(sculptor_instance_: SculptorInstance) -> None:
    """A turn with parallel slow bash, background task, and long foreground command should complete."""
    task_page = create_workspace_and_send(
        sculptor_instance_,
        "Do ALL of the following steps in order, in a SINGLE turn. Do not skip any step.\n\n"
        + "Step 1: Run THREE Bash commands IN PARALLEL (three separate Bash tool calls in the SAME response). "
        + "Each one runs: python3 -c \"import time; time.sleep(5); print('PARALLEL-DONE')\"\n\n"
        + "Step 2: After step 1 completes, run a Bash command with run_in_background set to true: "
        + "python3 -c \"import time; time.sleep(10); print('BG-DONE')\"\n\n"
        + "Step 3: After launching the background task, use the Grep tool to search for "
        + "'class ClaudeProcessManager' in the file sculptor/sculptor/agents/default/claude_code_sdk/process_manager.py\n\n"
        + "Step 4: Run a Bash command (foreground, NOT background): "
        + "python3 -c \"import time; time.sleep(10); print('LONG-FG-DONE')\"\n\n"
        + "Step 5: Reply with exactly: ALL-STEPS-COMPLETE-49182",
        wait_for_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Use the settle helper so the alpha mid-turn pill flicker (the
    # StatusPill unmounts briefly between sub-tools) doesn't cause this
    # check to return at 0s before the agent has actually finished. Use
    # a generous timeout — the turn involves ~25s of parallel sleeps +
    # 10s background + grep + 10s foreground sleep + Claude thinking time.
    wait_for_thinking_indicator_to_settle(chat_panel, timeout_ms=180_000)

    assert_any_message_contains(chat_panel, "ALL-STEPS-COMPLETE-49182")
    assert_no_errors(chat_panel)
