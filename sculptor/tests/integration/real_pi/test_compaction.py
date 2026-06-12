"""Real pi integration test: compaction chrome truthfulness.

HONEST SCOPING (REQ-TEST-1 divergence clause). The deterministic contract —
a compaction shows the "Compacting" StatusPill while active and clears it
after, across all reasons and the stuck-pill edges — is carried by the
deterministic tiers:

- unit: ``agent_wrapper_test`` (start→AutoCompacting; end→Done;
  aborted/error end still clears; willRetry extends the turn; start-without-end
  synthesizes a Done so the pill can't stick),
- fake_pi integration: ``test_pi_capability_gating.test_compaction_chrome_truthful_under_pi``
  (a scripted compaction held open shows then clears the pill under pi).

A REAL threshold compaction can't be triggered cheaply or reliably (it depends
on the upstream model filling the context window), and Sculptor exposes no
manual ``/compact`` surface to force one (Claude has none either — parity bar).
So this real-pi test mirrors the *chrome-truthfulness* contract at the altitude
real pi can guarantee: a normal turn against real pi completes cleanly with no
error, and the compaction chrome never gets stuck on "Compacting". If the turn
happens to compact opportunistically, the same assertions still hold — the pill
must have cycled back to clear by the time the turn finishes.
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
    # (create_pi_workspace_and_send waits for the turn to complete). A stuck
    # pill is the dangerous failure mode this capability must avoid.
    expect(sculptor_instance_.page.get_by_test_id(ElementIDs.STATUS_PILL_LABEL)).to_have_count(0)
