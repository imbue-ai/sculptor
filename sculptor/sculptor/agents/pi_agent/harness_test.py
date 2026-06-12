"""Tests for `PiHarness`'s identity and capability set."""

from sculptor.agents.pi_agent.harness import PI_HARNESS
from sculptor.interfaces.agents.harness import HarnessCapabilities
from sculptor.interfaces.environments.agent_execution_environment import Dependency


def test_pi_harness_capabilities() -> None:
    # Pi is a degraded harness: a capability is true only where Sculptor has a
    # pi-side mechanism for it (see PiHarness.capabilities for the per-flag why).
    assert PI_HARNESS.capabilities() == HarnessCapabilities(
        supports_interactive_backchannel=False,
        supports_skills=True,
        supports_sub_agents=False,
        supports_image_input=False,
        supports_fast_mode=False,
        supports_context_reset=False,
        supports_compaction=False,
        supports_background_tasks=False,
        supports_session_resume=True,
        supports_tool_use_rendering=True,
        supports_file_attachments=False,
        supports_interruption=True,
        supports_file_references=True,
    )


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
