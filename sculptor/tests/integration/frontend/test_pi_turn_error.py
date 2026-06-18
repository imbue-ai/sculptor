"""A failed pi turn surfaces a clean, actionable error in the chat.

When a pi turn fails mid-run (e.g. the selected model's provider has no key),
pi emits an assistant ``message_end`` with ``stopReason:"error"`` and an empty
body carrying the reason on ``errorMessage`` (no in-stream error event). Pi
must lift that reason into a clean, actionable error block — not the generic
"pi message ended in error" placeholder that drops pi's reason entirely.

FakePi scripts that exact wire shape via the ``fake_pi:turn_error`` directive.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.fake_pi import install_fake_pi_binary
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to see a clean, actionable error when a pi turn fails instead of a raw placeholder")
def test_failed_pi_turn_shows_clean_actionable_error(
    sculptor_instance_: SculptorInstance,
) -> None:
    install_fake_pi_binary(sculptor_instance_.fake_bin_dir)
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        workspace_name="Pi Turn Error",
        model_name=None,
        agent_type="pi",
    )

    chat_panel = task_page.get_chat_panel()
    # Drive FakePi to fail this turn mid-run with a provider-auth reason — the
    # shape real pi emits when the selected model's provider has no key.
    send_chat_message(
        chat_panel,
        'fake_pi:turn_error `{"message": "401 Authentication Fails, Your api key is invalid"}`',
    )

    # Target the per-turn failure block by its clean text. A failed pi turn also
    # tears the agent down, so a second, redundant "Agent crashed" error block
    # renders alongside this one (the known double-block; see the pi error
    # follow-up) — filtering keeps this assertion scoped to the clean block and
    # forward-compatible if that redundant block is later removed.
    clean_block = chat_panel.get_error_block().filter(has_text="Try another model")
    expect(clean_block).to_be_visible(timeout=60_000)
    # pi's real reason is preserved as detail so debugging isn't lost.
    expect(clean_block).to_contain_text("401 Authentication Fails")
    # The generic placeholder must NOT be what the user sees in any error block.
    expect(chat_panel.get_error_block().filter(has_text="pi message ended in error")).to_have_count(0)
