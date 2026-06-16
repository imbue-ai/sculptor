"""Real pi integration tests: sub-agent rendering and clean child shutdown.

Drives a real ``pi --mode rpc`` subprocess that loads the pinned
``sculptor_subagent`` extension, prompts it to delegate a trivial task to one
child sub-agent, and asserts the child's activity renders as the nested
AlphaSubagentPill (parent entry + attributed child activity) — the end-to-end
``supports_sub_agents`` path: extension → structured per-child payload over the
tool-execution lane → adapter → ``parent_tool_use_id`` grouping → pill.

A second test exercises abort composition (implementation plan §10.1.2): a
sub-agent whose child is mid-run is interrupted via Stop, and no orphan child
``pi`` process is left behind — the nested-case extension of the no-zombie
assertion.

Divergence note (REQ-TEST-1): there is no ``real_claude`` sub-agent *rendering*
test to mirror (Claude's sub-agent suite lives in the deterministic
``frontend/`` tests); the closest Claude real test is
``real_claude/test_stop_kills_foreground_subprocess.py``, whose no-orphan intent
the abort test below mirrors for the nested pi case.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.sculptor_instance import SculptorInstance
from tests.integration.real_pi.helpers import RESPONSE_TIMEOUT_MS
from tests.integration.real_pi.helpers import assert_no_errors
from tests.integration.real_pi.helpers import count_processes_matching
from tests.integration.real_pi.helpers import create_pi_workspace_and_send
from tests.integration.real_pi.helpers import interrupt_agent
from tests.integration.real_pi.helpers import real_pi
from tests.integration.real_pi.helpers import send_no_wait
from tests.integration.real_pi.helpers import wait_for_process_count


def _is_child_pi(cmdline: Sequence[str]) -> bool:
    """A live child sub-agent process: ``pi --mode json -p --no-session``.

    The long-lived parent agent is ``--mode rpc``, so matching ``--mode json``
    isolates children. Used to assert children exit (clean run) and are killed on
    abort (no orphans).
    """
    return "--mode" in cmdline and "json" in cmdline and "pi" in " ".join(cmdline)


@real_pi
@pytest.mark.timeout(600)
def test_pi_subagent_renders_nested_group_and_completes_cleanly(sculptor_instance_: SculptorInstance) -> None:
    """One parent, one child: the child's activity renders as the subagent pill,
    the turn completes without error, and no child pi process is left running."""
    baseline_children = count_processes_matching(_is_child_pi)
    prompt = (
        "Use your subagent tool to delegate exactly one task to a single sub-agent. "
        + 'Pass this as the task: "Run the shell command: echo PI-SUBAGENT-CHILD-50231". '
        + "Do not run the command yourself — delegate it via the subagent tool. "
        + "After the sub-agent reports back, reply with exactly: SUBAGENT-DONE-50231."
    )
    task_page = create_pi_workspace_and_send(sculptor_instance_, prompt)
    chat_panel = task_page.get_chat_panel()

    # The sub-agent's activity renders as the nested pill (parent entry + child).
    expect(sculptor_instance_.page.get_by_test_id(ElementIDs.ALPHA_CHAT_SUBAGENT_PILL).first).to_be_visible(
        timeout=RESPONSE_TIMEOUT_MS
    )
    expect(chat_panel.get_assistant_messages().last).to_contain_text("SUBAGENT-DONE-50231")
    assert_no_errors(chat_panel)
    expect(chat_panel.get_in_progress_tool_calls()).to_have_count(0)

    # No orphan child processes: the children exited when the tool finished.
    remaining = wait_for_process_count(_is_child_pi, baseline_children, at_least=False, timeout_s=20)
    assert remaining <= baseline_children, (
        f"orphan child pi processes after clean run: {remaining} > {baseline_children}"
    )


@real_pi
@pytest.mark.timeout(600)
def test_pi_subagent_abort_leaves_no_orphan_children(sculptor_instance_: SculptorInstance) -> None:
    """Stopping a turn while a sub-agent child is mid-run kills the child — no
    orphan ``pi`` process survives the interrupt (abort composition, §10.1.2)."""
    baseline_children = count_processes_matching(_is_child_pi)
    task_page = create_pi_workspace_and_send(
        sculptor_instance_,
        "Reply with exactly the text PI-READY-50232. Do not add any other text.",
    )
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel.get_assistant_messages().last).to_contain_text("PI-READY-50232")

    # Delegate a long-running child task, then interrupt while it runs.
    send_no_wait(
        chat_panel,
        "Use your subagent tool to delegate exactly one task to a single sub-agent. "
        + 'Pass this as the task: "Run the shell command: sleep 120". '
        + "Delegate it via the subagent tool; do not run it yourself.",
    )
    # Wait until the child sub-agent process is actually running.
    appeared = wait_for_process_count(_is_child_pi, baseline_children + 1, at_least=True, timeout_s=120)
    assert appeared > baseline_children, "sub-agent child process never started"

    interrupt_agent(chat_panel)

    # The child process tree is torn down by the extension's abort handler.
    remaining = wait_for_process_count(_is_child_pi, baseline_children, at_least=False, timeout_s=30)
    assert remaining <= baseline_children, f"orphan child pi processes after Stop: {remaining} > {baseline_children}"
