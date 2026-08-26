"""Unit tests for output_processor pure helpers."""

from __future__ import annotations

import pytest

from sculptor.agents.pi_agent.output_processor import AgentMessage
from sculptor.agents.pi_agent.output_processor import humanize_pi_failure_reason
from sculptor.agents.pi_agent.output_processor import humanize_transient_failure_reason
from sculptor.agents.pi_agent.output_processor import is_transient_provider_error
from sculptor.agents.pi_agent.output_processor import sum_message_usage


def test_agent_message_maps_camelcase_error_message() -> None:
    """A failed turn's `errorMessage` is parsed onto `error_message` (camel alias)."""
    message = AgentMessage.model_validate(
        {"role": "assistant", "content": [], "stopReason": "error", "errorMessage": "401 Authentication Fails"}
    )
    assert message.error_message == "401 Authentication Fails"
    assert message.stop_reason == "error"


def test_agent_message_maps_camelcase_usage() -> None:
    """An assistant message's `usage.{input,output}` is parsed onto the typed model."""
    message = AgentMessage.model_validate(
        {
            "role": "assistant",
            "content": [{"type": "text", "text": "hi"}],
            "stopReason": "stop",
            "usage": {"input": 100, "output": 50, "cacheRead": 0, "cacheWrite": 0},
        }
    )
    assert message.usage is not None
    assert message.usage.input == 100
    assert message.usage.output == 50


def test_sum_message_usage_totals_assistant_usage() -> None:
    """Usage is summed across assistant messages; non-assistant and usage-less messages are skipped."""
    messages = [
        AgentMessage.model_validate({"role": "user", "content": [], "usage": {"input": 999, "output": 999}}),
        AgentMessage.model_validate({"role": "assistant", "content": [], "usage": {"input": 100, "output": 40}}),
        AgentMessage.model_validate({"role": "assistant", "content": []}),
        AgentMessage.model_validate({"role": "assistant", "content": [], "usage": {"input": 30, "output": 10}}),
    ]
    assert sum_message_usage(messages) == (130, 50)


def test_sum_message_usage_returns_none_when_no_usage() -> None:
    """No assistant usage (e.g. an interrupted turn) yields (None, None)."""
    messages = [
        AgentMessage.model_validate({"role": "assistant", "content": [], "stopReason": "aborted"}),
    ]
    assert sum_message_usage(messages) == (None, None)


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


@pytest.mark.parametrize(
    "error_message",
    [
        '{"type": "overloaded_error", "message": "Overloaded"}',
        '{"type": "error", "error": {"type": "overloaded_error"}}',
        '{"type": "rate_limit_error", "message": "rate limit exceeded"}',
        '{"type": "api_error", "message": "Internal server error"}',
        "Request timed out after 600s",
        "Provider returned status 503",
        "429 Too Many Requests",
    ],
)
def test_transient_provider_errors_are_recognized(error_message: str) -> None:
    """overloaded / rate-limit / 5xx / timeout conditions classify as retryable."""
    assert is_transient_provider_error(error_message)


@pytest.mark.parametrize(
    "error_message",
    [
        None,
        "",
        "   ",
        "oops",
        "401 Authentication Fails, Your api key: ****0000 is invalid",
        '{"type": "authentication_error"}',
        '{"type": "invalid_request_error", "message": "max_tokens too large"}',
        "Model not found: deepseek/deepseek-v4-flash",
        "API error 400: Could not process image",
    ],
)
def test_terminal_errors_are_not_classified_transient(error_message: str | None) -> None:
    """Auth / unknown-model / validation / empty reasons are terminal, not retryable."""
    assert not is_transient_provider_error(error_message)


def test_humanize_transient_failure_leads_with_retry_guidance_and_keeps_detail() -> None:
    raw = '{"type": "overloaded_error", "message": "Overloaded"}'
    out = humanize_transient_failure_reason(raw)
    assert "try again" in out.lower()
    # The raw provider reason is preserved as detail so debugging isn't lost.
    assert raw in out


def test_humanize_transient_failure_empty_reason_is_clean() -> None:
    out = humanize_transient_failure_reason("")
    assert out
    assert "try again" in out.lower()
    assert humanize_transient_failure_reason(None) == out
