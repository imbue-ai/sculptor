"""Real pi integration test: compaction chrome truthfulness.

A real threshold compaction can't be triggered cheaply or reliably (it depends
on the upstream model filling the context window), and Sculptor exposes no
manual ``/compact`` surface to force one. The deterministic contract — a
compaction shows the "Compacting" StatusPill while active and clears it after,
across all reasons and the stuck-pill edges — is covered at the unit tier
(``agent_wrapper_test``) and the fake_pi integration tier
(``test_pi_capability_gating.test_compaction_chrome_truthful_under_pi``).

This real-pi test covers what real pi can guarantee: a normal turn completes
cleanly with no error and the compaction chrome never gets stuck on
"Compacting". If the turn happens to compact opportunistically, the same
assertions still hold.
"""

import pytest
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.sculptor_instance import SculptorInstance
from tests.integration.real_pi.helpers import create_pi_workspace_and_send
from tests.integration.real_pi.helpers import real_pi


@real_pi
@pytest.mark.timeout(300)
def test_compaction_chrome_does_not_stick_after_real_turn(sculptor_instance_: SculptorInstance) -> None:
    """A real pi turn completes with no error and leaves the Compacting chrome cleared."""
    task_page = create_pi_workspace_and_send(
        sculptor_instance_,
        "List the first five prime numbers, each on its own line, then stop.",
    )
    chat_panel = task_page.get_chat_panel()
    # The turn produced a real response and surfaced no error.
    expect(chat_panel.get_assistant_messages().last).not_to_be_empty()
    expect(chat_panel.get_error_block()).to_have_count(0)
    # Chrome truthfulness: whether or not pi compacted during the turn, the
    # "Compacting" StatusPill must not be stuck once the turn has finished
    # (create_pi_workspace_and_send waits for the turn to complete).
    expect(sculptor_instance_.page.get_by_test_id(ElementIDs.STATUS_PILL_LABEL)).to_have_count(0)
