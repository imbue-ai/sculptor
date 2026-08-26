"""Real Claude integration tests: Monitor tool.

Verifies that the Monitor tool's post-notification follow-up turn is fully
delivered. Monitor differs from Bash run_in_background: when its underlying
bash exits, the CLI emits ``task_updated{completed}`` and then a *follow-up*
turn (init -> assistant -> result) carrying the agent's reaction to the
streamed event.

Without the deferred-completion path in
``output_processor._DEFERRED_COMPLETION_TOOLS``, the output loop clears the
pending Monitor task at the current turn's result/success and exits — Sculptor
then SIGTERMs the CLI before it can emit the follow-up turn.

The test asserts that the follow-up turn *ran at all*: the agent emits
``MONITOR-FIRED-RECEIVED-91827`` inside turn 2, which only reaches the CLI
session transcript if the deferred-completion handoff kept the loop alive
across the turn-1 → turn-2 boundary. With the bug, turn 2 is never delivered
(the CLI is torn down at turn 1's result) and the marker is absent.

An earlier version of this test tried to hold the loop open longer by asking
the agent to run a foreground Bash ``sleep 8`` in turn 2 and emit a marker
afterward. That is unreliable: a foreground tool is not tracked in
``_pending_background_tasks`` and its ``task_started`` can arrive after the
turn's ``result``, so Sculptor SIGTERMs the CLI mid-sleep regardless of the
deferred-completion fix (SCU-1775). Asserting on the turn's delivery instead
of a post-foreground-tool marker avoids that unrelated race.
"""

import pytest

from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.sculptor_instance import SculptorInstance
from tests.integration.real_claude.helpers import create_workspace_and_send
from tests.integration.real_claude.helpers import get_message_text
from tests.integration.real_claude.helpers import get_transcript_messages
from tests.integration.real_claude.helpers import get_transcript_path
from tests.integration.real_claude.helpers import read_transcript
from tests.integration.real_claude.helpers import real_claude

_TRANSCRIPT_POLL_TIMEOUT_MS = 150_000
_TRANSCRIPT_POLL_INTERVAL_MS = 1_000


def _wait_for_assistant_marker_in_transcript(
    sculptor_instance: SculptorInstance,
    task_page: PlaywrightTaskPage,
    marker: str,
    *,
    timeout_ms: int = _TRANSCRIPT_POLL_TIMEOUT_MS,
) -> None:
    """Poll until ``marker`` lands in an assistant message of the CLI session transcript.

    Polls the diagnostics endpoint to discover the transcript file path
    (``None`` until the CLI emits its first init message), then polls the
    transcript file itself until the marker appears in an assistant text
    block.

    Polling the transcript directly avoids two UI-layer pitfalls:
      - ``ThinkingIndicator.not_to_be_visible`` returns eagerly during the
        inter-turn pause between turn 1's result and turn 2's init.
      - ``assistant_messages.last`` matches whichever message the agent
        emitted most recently, so a marker from an earlier turn — e.g. our
        turn 1 ``MONITOR-ARMED-91827`` after the agent has gone on to a
        third "task completed" turn — never matches ``last`` even though
        it's visible somewhere in the chat.
    """
    page = task_page._page
    elapsed_ms = 0
    while elapsed_ms < timeout_ms:
        try:
            transcript_path = get_transcript_path(sculptor_instance, task_page)
        except AssertionError:
            # Diagnostics returns transcriptFilePath=None until the CLI
            # emits its first init message. Keep polling.
            transcript_path = None
        if transcript_path is not None:
            transcript = read_transcript(transcript_path)
            for entry in get_transcript_messages(transcript, role="assistant"):
                if marker in get_message_text(entry):
                    return
        page.wait_for_timeout(_TRANSCRIPT_POLL_INTERVAL_MS)
        elapsed_ms += _TRANSCRIPT_POLL_INTERVAL_MS
    raise AssertionError(
        f"Marker {marker!r} did not appear in any assistant message of the CLI session transcript "
        + f"within {timeout_ms / 1000:.0f}s."
    )


@real_claude
@pytest.mark.timeout(240)
def test_monitor_tool_post_notification_turn_runs(sculptor_instance_: SculptorInstance) -> None:
    """Monitor's follow-up event-delivery turn actually executes.

    Repro: instruct the agent to arm the Monitor tool with a bash command
    that emits one stdout line and exits. The CLI then emits two turns:

      Turn 1: init -> assistant calls Monitor + says STAGE_ONE -> result
              ... (mid-turn) task_started, task_updated{completed}
      Turn 2: init -> assistant reacts to the streamed event -> result

    Without the fix, ``task_updated{completed}`` for Monitor goes into
    ``_completed_via_task_updated`` immediately, so cleanup at turn 1's
    result/success drops ``_pending_background_tasks`` to empty, the output
    loop exits, and Sculptor SIGTERMs the CLI process before turn 2 runs — so
    ``MONITOR-FIRED-RECEIVED-91827`` is never emitted.

    With the fix, Monitor's completion is deferred via
    ``_completed_pending_deferred`` until turn 2's init promotes it. The loop
    stays alive across the handoff, turn 2 executes, and its
    ``MONITOR-FIRED-RECEIVED-91827`` reply lands in the CLI session transcript
    as an assistant message.

    The test asserts on the CLI session transcript rather than the chat UI:
    the marker is emitted inside the follow-up turn, so its presence in the
    CLI's own session file is unambiguous proof the deferred follow-up turn
    was delivered rather than dropped.
    """
    prompt = (
        "Use the Monitor tool RIGHT NOW with these exact parameters:\n"
        + "  command: echo MONITOR_FIRED_PAYLOAD_91827\n"
        + "  description: monitor-deferred-completion-91827\n"
        + "  timeout_ms: 30000\n"
        + "  persistent: false\n"
        + "\n"
        + "The Monitor's bash command emits the line MONITOR_FIRED_PAYLOAD_91827 once and exits immediately on its own.\n"
        + "\n"
        + "Step 1: After arming the Monitor (you'll get a tool_result confirming it started), reply with exactly:\n"
        + "    MONITOR-ARMED-91827\n"
        + "Then end your turn. Critically:\n"
        + "- Do NOT call any further tools at this point.\n"
        + "- Do NOT add commentary or analysis.\n"
        + "\n"
        + "Step 2: Shortly after, you will receive a system notification containing MONITOR_FIRED_PAYLOAD_91827. "
        + "When you receive it, reply with exactly:\n"
        + "    MONITOR-FIRED-RECEIVED-91827\n"
        + "Then stop. Do not call any further tools and do not add commentary.\n"
    )
    task_page = create_workspace_and_send(sculptor_instance_, prompt, wait_for_finish=False)

    # Assert on the follow-up event-delivery turn actually running: MONITOR-FIRED-RECEIVED-91827
    # is emitted inside turn 2, which only happens if Monitor's deferred completion kept the
    # output loop alive across the handoff (SCU-1669). Without the fix, the loop clears the
    # pending Monitor task at turn 1's result and Sculptor SIGTERMs the CLI before turn 2 runs,
    # so the marker never reaches the transcript.
    #
    # We deliberately do NOT gate this on a marker emitted after a foreground Bash in turn 2:
    # a foreground tool is not tracked in _pending_background_tasks and its task_started can
    # arrive after the turn's result, so Sculptor tears the CLI down mid-execution regardless of
    # the deferred-completion fix (SCU-1775). Asserting on the turn's delivery avoids that race.
    _wait_for_assistant_marker_in_transcript(sculptor_instance_, task_page, "MONITOR-FIRED-RECEIVED-91827")
