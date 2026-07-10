"""Real pi integration test: session resume across an agent-process restart.

Plants a codeword on a real ``pi --mode rpc`` turn, restarts the whole Sculptor
instance (the clean agent-restart lever — pi has no UI Stop button, since
``supports_interruption`` is false), then asks the resumed agent to recall the
codeword. A correct recall proves PiAgent's ``--session-dir``/``--session-id``
relaunch restored the real session's context.

Also logs the session JSONL file size before and after — an informational bound
on file growth (architecture §4.7), not an assertion.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from tests.integration.real_pi.helpers import RESPONSE_TIMEOUT_MS
from tests.integration.real_pi.helpers import prefixed
from tests.integration.real_pi.helpers import real_pi

_SENTINEL = "PINEAPPLE-77"


def _log_session_file_sizes(sculptor_folder: Path, when: str) -> None:
    """Log every pi session JSONL under the sculptor folder + its size.

    Informational only (the growth bound is not asserted). Pi stores the
    session under ``{workspace_root}/state/tasks/{task_id}/pi_session/``.
    """
    files = sorted(Path(sculptor_folder).glob("**/pi_session/*.jsonl"))
    if not files:
        print(f"[real_pi resume] ({when}) no pi_session/*.jsonl found under {sculptor_folder}")
        return
    for session_file in files:
        print(f"[real_pi resume] ({when}) {session_file.name}: {session_file.stat().st_size} bytes")


@real_pi
@pytest.mark.timeout(600)
def test_real_pi_recalls_sentinel_across_restart(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    # Instance 1: plant the codeword and let the turn complete (persisted to the
    # real pi session file).
    with sculptor_instance_factory_.spawn_instance() as instance:
        task_page = start_task_and_wait_for_ready(
            sculptor_page=instance.page,
            workspace_name="Real Pi Resume",
            prompt=prefixed(f"Remember this codeword: {_SENTINEL}. Reply with exactly OK and nothing else."),
            model_name=None,
            agent_type="pi",
        )
        chat_panel = task_page.get_chat_panel()
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=RESPONSE_TIMEOUT_MS)
        _log_session_file_sizes(instance.sculptor_folder, when="after plant")

    # Instance 2: the backend and the pi agent process restart. Re-opening the
    # workspace re-runs the agent, which resumes the persisted session; the
    # recall must surface the pre-restart codeword.
    with sculptor_instance_factory_.spawn_instance() as instance:
        workspace_row = get_workspace_sidebar(instance.page).get_workspace_rows().first
        expect(workspace_row).to_be_visible()
        workspace_row.click()
        task_page = PlaywrightTaskPage(page=instance.page)
        chat_panel = task_page.get_chat_panel()
        expect(chat_panel).to_be_visible()

        send_chat_message(
            chat_panel=chat_panel,
            message=prefixed(
                "What codeword did I ask you to remember earlier? Reply with exactly that codeword and nothing else."
            ),
        )
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4, timeout=RESPONSE_TIMEOUT_MS)
        expect(chat_panel.get_assistant_messages().last).to_contain_text(_SENTINEL)
        expect(chat_panel.get_error_block()).to_have_count(0)
        _log_session_file_sizes(instance.sculptor_folder, when="after recall")
