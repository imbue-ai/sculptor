"""Integration tests for the pi interactive backchannel (FakePi-driven).

Exercise the full ask-user-question and plan-mode round-trips end-to-end on a
pi workspace: FakePi's ``ui_request`` directive emits the ``extension_ui_request``
the real ``sculptor_backchannel`` extension's dialogs produce, Sculptor maps it
onto the Q&A panel, and the user's answer is routed back as the matching
``extension_ui_response`` (which FakePi echoes into the turn as ``ANSWER=<value>``).

Pi does not render tool blocks yet (``supports_tool_use_rendering`` is False), so
unlike the Claude AUQ/plan suites these assert on the Q&A panel and the answer
the agent receives, not on AUQ/ExitPlanMode tool blocks.
"""

from playwright.sync_api import expect

from sculptor.agents.pi_agent.backchannel import PLAN_APPROVAL_DIALOG_TITLE
from sculptor.testing.elements.ask_user_question import get_ask_user_question_panel
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.fake_pi import install_fake_pi_binary
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

_SELECT_QUESTION_PROMPT = (
    'fake_pi:ui_request `{"method": "select", "title": "Tea or coffee?", "options": ["tea", "coffee"]}`'
)

# A plan-mode turn: present a plan as text, then open the plan-approval dialog
# (the sentinel title the real extension's exit_plan_mode tool uses).
_PLAN_PROMPT = (
    'fake_pi:emit_text `{"text": "My plan: step 1, step 2."}` '
    + f'fake_pi:ui_request `{{"method": "select", "title": "{PLAN_APPROVAL_DIALOG_TITLE}", "options": ["Approve plan"]}}`'
)


def _start_pi_workspace(sculptor_instance_: SculptorInstance, prompt: str, workspace_name: str) -> PlaywrightTaskPage:
    install_fake_pi_binary(sculptor_instance_.fake_bin_dir)
    return start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        workspace_name=workspace_name,
        model_name=None,
        agent_type="pi",
        prompt=prompt,
        wait_for_agent_to_finish=False,
    )


@user_story("to answer a question the pi agent asks mid-turn")
def test_pi_ask_user_question_round_trip(sculptor_instance_: SculptorInstance) -> None:
    """The pi agent asks a multiple-choice question; the user answers; the agent uses it."""
    page = sculptor_instance_.page
    task_page = _start_pi_workspace(sculptor_instance_, _SELECT_QUESTION_PROMPT, "Pi AUQ")
    chat_panel = task_page.get_chat_panel()

    # The Q&A panel appears with the question and options.
    ask_panel = get_ask_user_question_panel(page)
    expect(ask_panel).to_be_visible(timeout=30_000)
    expect(ask_panel.get_question_text()).to_contain_text("Tea or coffee?")
    expect(ask_panel.get_submit_button()).to_be_disabled()

    # Answer it; the chat input returns and the agent resumes.
    ask_panel.select_option("coffee")
    ask_panel.submit()
    expect(ask_panel).not_to_be_visible(timeout=30_000)
    expect(chat_panel.get_chat_input()).to_be_visible()

    # The agent received the answer and used it (FakePi echoes ANSWER=<value>).
    expect(chat_panel.get_thinking_indicator(), "agent to finish").not_to_be_visible()
    expect(chat_panel.get_assistant_messages().filter(has_text="ANSWER=coffee").first).to_be_visible()


@user_story("to give the pi agent a free-form answer via the Other affordance")
def test_pi_ask_user_question_free_text(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    task_page = _start_pi_workspace(sculptor_instance_, _SELECT_QUESTION_PROMPT, "Pi AUQ Free Text")
    chat_panel = task_page.get_chat_panel()

    ask_panel = get_ask_user_question_panel(page)
    expect(ask_panel).to_be_visible(timeout=30_000)
    ask_panel.select_option("Other")
    ask_panel.type_other_text("herbal tea")
    ask_panel.submit()

    expect(ask_panel).not_to_be_visible(timeout=30_000)
    expect(chat_panel.get_thinking_indicator(), "agent to finish").not_to_be_visible()
    expect(chat_panel.get_assistant_messages().filter(has_text="ANSWER=herbal tea").first).to_be_visible()


@user_story("to dismiss a question the pi agent asks")
def test_pi_ask_user_question_dismiss(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    task_page = _start_pi_workspace(sculptor_instance_, _SELECT_QUESTION_PROMPT, "Pi AUQ Dismiss")
    chat_panel = task_page.get_chat_panel()

    ask_panel = get_ask_user_question_panel(page)
    expect(ask_panel).to_be_visible(timeout=30_000)
    ask_panel.dismiss()

    expect(ask_panel).not_to_be_visible(timeout=30_000)
    expect(chat_panel.get_thinking_indicator(), "agent to finish").not_to_be_visible()
    # The extension's dialog resolved to a cancellation; FakePi echoes the
    # dismissal sentinel.
    expect(chat_panel.get_assistant_messages().filter(has_text="ANSWER=[dismissed]").first).to_be_visible()


@user_story("to enter plan mode on pi, review the plan, and approve it")
def test_pi_plan_mode_enter_and_approve(sculptor_instance_: SculptorInstance) -> None:
    """Toggle plan mode on, send a request, approve the presented plan; plan mode clears."""
    page = sculptor_instance_.page
    # First turn just gets the workspace to ready with the chat input visible.
    task_page = _start_pi_workspace(sculptor_instance_, 'fake_pi:emit_text `{"text": "ready"}`', "Pi Plan Mode")
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel.get_thinking_indicator(), "first turn to finish").not_to_be_visible()

    # Turn the plan-first toggle on, then send the planning request.
    toggle = chat_panel.get_plan_mode_toggle()
    expect(toggle).to_be_visible()
    toggle.click()
    expect(toggle).to_have_attribute("data-active", "true")
    send_chat_message(chat_panel=chat_panel, message=_PLAN_PROMPT)

    # The plan-approval prompt appears (the canonical Sculptor plan question).
    ask_panel = get_ask_user_question_panel(page)
    expect(ask_panel).to_be_visible(timeout=30_000)
    expect(ask_panel.get_question_text()).to_contain_text("How would you like to proceed")
    expect(ask_panel.get_options().filter(has_text="Approve plan").first).to_be_visible()

    # Approve; plan mode clears and the agent proceeds.
    ask_panel.select_option("Approve plan")
    ask_panel.submit()
    expect(ask_panel).not_to_be_visible(timeout=30_000)

    toggle = chat_panel.get_plan_mode_toggle()
    expect(toggle).to_be_visible()
    expect(toggle).to_have_attribute("data-active", "false")
    expect(chat_panel.get_thinking_indicator(), "agent to finish").not_to_be_visible()
    expect(chat_panel.get_assistant_messages().filter(has_text="ANSWER=Approve plan").first).to_be_visible()
