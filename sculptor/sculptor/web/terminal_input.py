"""Shared, identically-gated PTY-write path for registered terminal agents.

The reverse channel that lets Sculptor features reach a TUI as if the user
typed the prompt. Both the `/terminal/input` endpoint and the CI Babysitter
write through this single helper so their security guards can never drift
apart. Kept framework-free (no FastAPI) so the coordinator can call it.
"""

import time
from enum import StrEnum

from loguru import logger

from sculptor.database.models import AgentTaskInputsV2
from sculptor.database.models import Task
from sculptor.interfaces.agents.agent import RegisteredTerminalAgentConfig
from sculptor.interfaces.agents.agent import TerminalStatusSignal
from sculptor.services.task_service.api import TaskService
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    get_terminal_manager,
)
from sculptor.tasks.handlers.run_terminal_agent.terminal_session import make_agent_terminal_id
from sculptor.web.derived import scan_terminal_signal_state

# Bracketed-paste markers: TUIs that support them (Claude Code's included)
# treat the wrapped block as one paste and do not auto-submit on embedded
# newlines, so the program — not us — controls submission.
_BRACKETED_PASTE_START = b"\x1b[200~"
_BRACKETED_PASTE_END = b"\x1b[201~"

# Pause between writing the bracketed-paste body and writing the submit Enter.
# A TUI (Claude Code) shows "Pasting text…" while it finalizes a bracketed
# paste; an Enter that arrives before it leaves paste mode is absorbed into the
# paste instead of submitting, so the prompt never lands and the driven turn
# never completes. Verified against real claude: the back-to-back write fails
# and ~0.2s suffices; this leaves margin for a loaded machine. The babysitter
# drive is off-thread so this costs it nothing; the endpoint adds <1s to a
# user-triggered submit.
_PASTE_SUBMIT_DELAY_SECONDS = 0.75


class TerminalDeliveryResult(StrEnum):
    """Outcome of attempting to write a prompt into a terminal agent's PTY.

    The caller maps it to an HTTP status (the endpoint) or a babysitter
    transient disabled-reason. Only DELIVERED means the bytes were written.
    """

    DELIVERED = "DELIVERED"
    NOT_OPT_IN = "NOT_OPT_IN"
    NOT_AT_PROMPT = "NOT_AT_PROMPT"
    NO_PTY = "NO_PTY"


def deliver_prompt_to_terminal_agent(
    task: Task,
    text: str,
    *,
    submit: bool = True,
    task_service: TaskService,
) -> TerminalDeliveryResult:
    """Write an automated prompt into a registered terminal agent's PTY.

    Runs the three security guards and performs the bracketed-paste write,
    returning a result enum instead of raising. Never raises HTTPException —
    mapping to HTTP belongs to the endpoint.
    """
    input_data = task.input_data

    # Guard 1: only registrations that opted in. Plain terminals and
    # non-opt-in registrations NEVER receive writes — a bare shell would
    # execute the prompt as commands. Re-checking the stamped config here
    # defends against a since-revoked opt-in.
    agent_config = input_data.agent_config if isinstance(input_data, AgentTaskInputsV2) else None
    if not isinstance(agent_config, RegisteredTerminalAgentConfig) or not agent_config.accepts_automated_prompts:
        return TerminalDeliveryResult.NOT_OPT_IN

    # Guard 2: the program must be at its prompt — the latest signal of the
    # CURRENT run must be IDLE or WAITING (answering a question is a primary
    # use case). "Run started but no signals yet" is NOT enough: a registered
    # agent whose hooks are broken degrades to plain-terminal behavior,
    # and we must not write into an unknown state. The check is
    # inherently racy (the program may go busy between check and write) —
    # acceptable: it prevents the systematic misuse, not a TOCTOU-proof lock.
    run_started, latest_signal = scan_terminal_signal_state(task_service.get_live_messages_for_task(task.object_id))
    if not run_started or latest_signal not in (TerminalStatusSignal.IDLE, TerminalStatusSignal.WAITING):
        return TerminalDeliveryResult.NOT_AT_PROMPT

    # Guard 3: a live PTY to write into.
    terminal_manager = get_terminal_manager(make_agent_terminal_id(task.object_id))
    if terminal_manager is None:
        return TerminalDeliveryResult.NO_PTY

    # Always bracketed-paste the body, then send the submit Enter as its OWN
    # write — mirrors how a human pastes then hits Enter. The Enter must never
    # share a write with the text: a real TUI (Claude Code) treats a large
    # single-burst write as a paste and swallows a trailing carriage return as a
    # literal newline instead of submitting, leaving the prompt in the composer
    # unsubmitted. (A short prompt stays under the paste threshold and would
    # submit either way, but the framing must not depend on length.) Bracketing
    # the body and separating the Enter makes submission reliable regardless of
    # the prompt's length or whether it spans multiple lines.
    terminal_manager.write(_BRACKETED_PASTE_START + text.encode() + _BRACKETED_PASTE_END)
    if submit:
        # Let the TUI leave "Pasting text…" before the Enter, so the Enter
        # submits the paste instead of being absorbed into it.
        time.sleep(_PASTE_SUBMIT_DELAY_SECONDS)
        terminal_manager.write(b"\r")
    # Log the event, never the text — prompts can embed user content.
    logger.info("Wrote automated prompt ({} chars) to terminal agent {}", len(text), task.object_id)
    return TerminalDeliveryResult.DELIVERED
