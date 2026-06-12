"""Basic end-to-end pi workspace through the UI.

Creates a workspace with ``harness=pi``, sends a user message, and asserts the
FakePi assistant response renders. Spot-checks that the most prominent
Claude-only affordances (plan-mode toggle, sub-agent pill, fast-mode toggle)
are suppressed and the skills panel renders its empty state. Per-capability
parity is the responsibility of test_pi_capability_gating.py.
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

    expect(page.get_by_test_id(ElementIDs.PLAN_MODE_TOGGLE)).to_have_count(0)
    expect(page.get_by_test_id(ElementIDs.FAST_MODE_TOGGLE)).to_have_count(0)
    expect(page.get_by_test_id(ElementIDs.ALPHA_CHAT_SUBAGENT_PILL)).to_have_count(0)

    # The skills panel renders an "Skills unavailable" empty state when the
    # harness reports !supportsSkills; assert no SkillChip elements render.
    expect(page.get_by_test_id(ElementIDs.SKILL_CHIP)).to_have_count(0)
