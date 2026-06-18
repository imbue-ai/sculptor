"""Tests for `PiHarness`'s identity, capability set, and gated methods."""

from sculptor.agents.pi_agent.backchannel import ASK_USER_QUESTION_TOOL_NAME
from sculptor.agents.pi_agent.backchannel import EXIT_PLAN_MODE_TOOL_NAME
from sculptor.agents.pi_agent.harness import PI_HARNESS
from sculptor.interfaces.agents.harness import HarnessCapabilities
from sculptor.interfaces.environments.agent_execution_environment import Dependency
from sculptor.primitives.ids import ToolUseID
from sculptor.state.chat_state import ToolUseBlock


def test_pi_harness_capabilities() -> None:
    # A capability is true only where Sculptor has a pi-side mechanism for it
    # (see PiHarness.capabilities for the per-flag why). Pi now carries every
    # flag but fast mode (no natural mapping to pi's models).
    assert PI_HARNESS.capabilities() == HarnessCapabilities(
        supports_chat_interface=True,
        supports_interactive_backchannel=True,
        supports_skills=True,
        supports_sub_agents=True,
        supports_image_input=True,
        supports_fast_mode=False,
        supports_context_reset=True,
        supports_compaction=True,
        supports_background_tasks=True,
        supports_session_resume=True,
        supports_tool_use_rendering=True,
        supports_file_attachments=True,
        supports_interruption=True,
        supports_file_references=True,
    )


def test_pi_harness_gated_methods_recognize_backchannel_tools() -> None:
    assert PI_HARNESS.is_ask_user_question_tool(ASK_USER_QUESTION_TOOL_NAME) is True
    assert PI_HARNESS.is_ask_user_question_tool("read") is False
    assert PI_HARNESS.is_exit_plan_mode_tool(EXIT_PLAN_MODE_TOOL_NAME) is True
    assert PI_HARNESS.is_exit_plan_mode_tool("write") is False


def test_pi_harness_validates_ask_user_question_input() -> None:
    # The AUQ tool's input is valid when it carries a non-empty question string.
    assert (
        PI_HARNESS.is_valid_ask_user_question_input(ASK_USER_QUESTION_TOOL_NAME, {"question": "Tea or coffee?"})
        is True
    )
    assert PI_HARNESS.is_valid_ask_user_question_input(ASK_USER_QUESTION_TOOL_NAME, {}) is False
    assert PI_HARNESS.is_valid_ask_user_question_input(ASK_USER_QUESTION_TOOL_NAME, {"question": ""}) is False
    # Non-AUQ tools always pass (mirrors the Claude harness convention).
    assert PI_HARNESS.is_valid_ask_user_question_input("read", {"path": "x"}) is True


def test_pi_harness_classifies_tool_ui_role() -> None:
    # The harness owns the name->role mapping; the conversion layer stamps the
    # result onto the block so the frontend renders by role, not by tool name.
    assert PI_HARNESS.classify_tool_ui_role(ASK_USER_QUESTION_TOOL_NAME) == "ask_user_question"
    assert PI_HARNESS.classify_tool_ui_role(EXIT_PLAN_MODE_TOOL_NAME) == "exit_plan_mode"
    assert PI_HARNESS.classify_tool_ui_role("read") is None


def test_pi_harness_reconstructs_pending_question_from_flat_tool_input() -> None:
    # Real pi persists the ask_user_question call as a tool block whose input is
    # the extension's flat {question, options} shape — NOT AskUserQuestionData.
    # The harness translates it back into the canonical question so a reloaded
    # page re-pends it (the base harness would reject this shape).
    block = ToolUseBlock(
        id=ToolUseID("tu_auq"),
        name=ASK_USER_QUESTION_TOOL_NAME,
        input={"question": "Tea or coffee?", "options": ["tea", "coffee"]},
    )
    reconstructed = PI_HARNESS.reconstruct_pending_ask_user_question(block)
    assert reconstructed is not None
    assert reconstructed.tool_use_id == "tu_auq"
    question = reconstructed.questions[0]
    assert question.question == "Tea or coffee?"
    assert [option.label for option in question.options] == ["tea", "coffee"]


def test_pi_harness_reconstructs_free_form_question_without_options() -> None:
    block = ToolUseBlock(id=ToolUseID("tu_free"), name=ASK_USER_QUESTION_TOOL_NAME, input={"question": "Your name?"})
    reconstructed = PI_HARNESS.reconstruct_pending_ask_user_question(block)
    assert reconstructed is not None
    assert reconstructed.questions[0].options == []


def test_pi_harness_skips_reconstruction_for_invalid_question_input() -> None:
    block = ToolUseBlock(id=ToolUseID("tu_bad"), name=ASK_USER_QUESTION_TOOL_NAME, input={"not_a_question": 1})
    assert PI_HARNESS.reconstruct_pending_ask_user_question(block) is None


def test_pi_harness_identity() -> None:
    assert PI_HARNESS.name == "pi"
    assert PI_HARNESS.binary_dependency == Dependency.PI


def test_pi_harness_hidden_system_prompt_is_populated() -> None:
    prompt = PI_HARNESS.hidden_system_prompt
    assert prompt.strip(), "Pi hidden_system_prompt must be populated"


def test_pi_hidden_system_prompt_names_sculptor() -> None:
    assert "Sculptor" in PI_HARNESS.hidden_system_prompt


def test_pi_hidden_system_prompt_avoids_claude_and_anthropic_branding() -> None:
    lowered = PI_HARNESS.hidden_system_prompt.lower()
    assert "claude" not in lowered, "Pi prompt must not mention Claude"
    assert "anthropic" not in lowered, "Pi prompt must not mention Anthropic"


def test_pi_hidden_system_prompt_declares_media_display_and_attachments() -> None:
    prompt = PI_HARNESS.hidden_system_prompt
    assert "MediaDisplay" in prompt, "Pi prompt must declare the MediaDisplay convention"
    assert "workspace attachments directory" in prompt, "Pi prompt must reference the workspace attachments directory"


def test_pi_hidden_system_prompt_omits_mcp_tool_instructions() -> None:
    lowered = PI_HARNESS.hidden_system_prompt.lower()
    assert "mcp__sculptor" not in lowered, "Pi has no Sculptor MCP tools — addendum must be absent"
    assert "askuserquestion" not in lowered
    assert "exitplanmode" not in lowered
