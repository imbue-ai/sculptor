"""Basic end-to-end pi workspace through the UI.

Creates a workspace with ``harness=pi``, sends a user message, and asserts the
FakePi assistant response renders. Spot-checks that the most prominent
Claude-only affordances (sub-agent pill, fast-mode toggle) are suppressed and
the skills panel renders its empty state. The plan-mode toggle is NOT here: pi
now supports the interactive backchannel, so that toggle is available — its
gating is covered by test_pi_capability_gating.py. Per-capability parity is the
responsibility of test_pi_capability_gating.py.
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.interfaces.agents.agent import HarnessName
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.fake_pi import install_fake_pi_binary
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to see a pi-harness workspace respond to a message with the FakePi default text")
def test_pi_workspace_basic_response(
    sculptor_instance_: SculptorInstance,
) -> None:
    install_fake_pi_binary(sculptor_instance_.fake_bin_dir)
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        workspace_name="Pi Basic",
        # The model field is unused by FakePi; skip the model-selector click so
        # the test does not rely on a "Fake Pi" entry being registered in the
        # LLMModel enum.
        model_name=None,
        harness=HarnessName.PI,
    )

    chat_panel = task_page.get_chat_panel()
    # FakePi's default response is emitted whenever neither system prompt nor
    # the per-turn message carries a directive, so a bare prompt produces a
    # deterministic assistant message.
    send_chat_message(chat_panel, "hello pi")
    wait_for_completed_message_count(chat_panel, expected_message_count=2)

    expect(chat_panel.get_assistant_messages().first).to_contain_text("FakePi")


@user_story("to reset a pi conversation with /clear so the agent no longer recalls earlier turns")
def test_pi_clear_resets_conversation(
    sculptor_instance_: SculptorInstance,
) -> None:
    """/clear under pi round-trips and genuinely restarts the conversation.

    FakePi remembers prior user turns (the session-resume hook); the
    ``fake_pi:recall`` directive surfaces them. After /clear sends ``new_session``,
    that memory is gone — so recall finds the planted sentinel BEFORE the clear
    and ``NO_PRIOR_CONTEXT`` AFTER it.
    """
    install_fake_pi_binary(sculptor_instance_.fake_bin_dir)
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        workspace_name="Pi Clear",
        model_name=None,
        harness=HarnessName.PI,
    )
    chat_panel = task_page.get_chat_panel()

    # Turn 1: plant a sentinel (FakePi records the user turn).
    send_chat_message(chat_panel, "SENTINEL-PINEAPPLE-4242 remember this")
    wait_for_completed_message_count(chat_panel, expected_message_count=2)

    # Turn 2: recall finds the planted sentinel — memory of prior turns works.
    send_chat_message(chat_panel, "fake_pi:recall")
    wait_for_completed_message_count(chat_panel, expected_message_count=4)
    expect(chat_panel.get_assistant_messages().last).to_contain_text("SENTINEL-PINEAPPLE-4242")

    # /clear via the pseudo-skill: the reset round-trips (Context Cleared summary renders).
    send_chat_message(chat_panel, "/clear")
    expect(chat_panel.get_context_summary_messages()).to_be_visible(timeout=60_000)

    # Turn 3: after the reset, recall finds no prior context — the conversation restarted.
    send_chat_message(chat_panel, "fake_pi:recall")
    expect(chat_panel.get_assistant_messages().last).to_contain_text("NO_PRIOR_CONTEXT", timeout=60_000)


@user_story("to see Claude-only affordances stay hidden in a pi workspace")
def test_pi_workspace_suppresses_claude_only_surfaces(
    sculptor_instance_: SculptorInstance,
) -> None:
    install_fake_pi_binary(sculptor_instance_.fake_bin_dir)
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        workspace_name="Pi Affordances",
        model_name=None,
        harness=HarnessName.PI,
    )

    chat_panel = task_page.get_chat_panel()
    # Wait for the chat input itself so the task object (and its
    # harnessCapabilities) has loaded into the workspace page before we assert
    # absence — `?? true` would otherwise mask the gates while the task is
    # still hydrating.
    expect(chat_panel.get_chat_input()).to_be_visible()
    expect(chat_panel.get_send_button()).to_be_visible()

    # The plan-mode toggle is intentionally NOT asserted absent here: pi now
    # supports the interactive backchannel, so the toggle renders (its gating is
    # covered by test_pi_capability_gating.py).
    expect(page.get_by_test_id(ElementIDs.FAST_MODE_TOGGLE)).to_have_count(0)
    expect(page.get_by_test_id(ElementIDs.ALPHA_CHAT_SUBAGENT_PILL)).to_have_count(0)

    # The skills panel renders an "Skills unavailable" empty state when the
    # harness reports !supportsSkills; assert no SkillChip elements render.
    expect(page.get_by_test_id(ElementIDs.SKILL_CHIP)).to_have_count(0)
