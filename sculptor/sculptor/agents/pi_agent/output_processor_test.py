"""Unit tests for output_processor pure helpers."""

from __future__ import annotations

from sculptor.agents.pi_agent.output_processor import AgentMessage
from sculptor.agents.pi_agent.output_processor import humanize_pi_failure_reason


def test_agent_message_maps_camelcase_error_message() -> None:
    """A failed turn's `errorMessage` is parsed onto `error_message` (camel alias)."""
    message = AgentMessage.model_validate(
        {"role": "assistant", "content": [], "stopReason": "error", "errorMessage": "401 Authentication Fails"}
    )
    assert message.error_message == "401 Authentication Fails"
    assert message.stop_reason == "error"


def test_humanize_auth_failure_leads_with_actionable_guidance_and_keeps_detail() -> None:
    out = humanize_pi_failure_reason("401 Authentication Fails, Your api key: ****0000 is invalid")
    assert "Try another model" in out
    # The clean guidance leads; pi's raw reason is preserved as detail.
    assert out.index("Try another model") < out.index("401 Authentication Fails")
    assert "401 Authentication Fails, Your api key: ****0000 is invalid" in out


def test_humanize_unknown_model_failure_is_actionable_and_keeps_detail() -> None:
    out = humanize_pi_failure_reason("Model not found: deepseek/deepseek-v4-flash")
    assert "Try another model" in out
    assert "Model not found: deepseek/deepseek-v4-flash" in out


def test_humanize_passes_through_already_human_readable_reason() -> None:
    """A reason pi already phrased for a human (no recognized failure shape) is surfaced unchanged."""
    reason = "API error 400: Could not process image"
    assert humanize_pi_failure_reason(reason) == reason


def test_humanize_empty_reason_gives_clean_generic_not_placeholder() -> None:
    out = humanize_pi_failure_reason("")
    assert out
    assert "pi message ended in error" not in out
    assert humanize_pi_failure_reason(None) == out
