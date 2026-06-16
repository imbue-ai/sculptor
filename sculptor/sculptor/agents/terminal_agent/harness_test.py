"""Tests for `TerminalHarness` and the terminal-config registry wiring."""

import pytest

from sculptor.agents.harness_registry import UnknownAgentConfigError
from sculptor.agents.harness_registry import create_agent_for_run
from sculptor.agents.harness_registry import get_harness_for_config
from sculptor.agents.terminal_agent.harness import TERMINAL_HARNESS
from sculptor.database.models import AgentTaskInputsV2
from sculptor.interfaces.agents.agent import RegisteredTerminalAgentConfig
from sculptor.interfaces.agents.agent import TerminalAgentConfig
from sculptor.interfaces.agents.harness import AgentRunContext
from sculptor.interfaces.agents.harness import HarnessCapabilities


def _make_registered_config() -> RegisteredTerminalAgentConfig:
    return RegisteredTerminalAgentConfig(
        registration_id="claude-code",
        display_name="Claude Code",
        launch_command="claude",
    )


def test_terminal_harness_capabilities_are_uniformly_false() -> None:
    # Iterate the model fields so a future capability cannot silently default:
    # terminal agents have no chat surface, so every field must be False.
    capabilities = TERMINAL_HARNESS.capabilities()
    for field_name in HarnessCapabilities.model_fields:
        assert getattr(capabilities, field_name) is False, f"{field_name} must be False for the terminal harness"


def test_terminal_harness_identity() -> None:
    assert TERMINAL_HARNESS.name == "terminal"


def test_get_harness_for_config_resolves_terminal_configs() -> None:
    assert get_harness_for_config(TerminalAgentConfig()) is TERMINAL_HARNESS
    assert get_harness_for_config(_make_registered_config()) is TERMINAL_HARNESS


def test_create_agent_for_run_rejects_terminal_configs() -> None:
    # Terminal configs are dispatched to the dedicated terminal task handler
    # and must never construct a chat `Agent`.
    task_data = AgentTaskInputsV2(agent_config=TerminalAgentConfig(), git_hash="abc123")
    context = AgentRunContext.model_construct(task_data=task_data)
    with pytest.raises(UnknownAgentConfigError):
        create_agent_for_run(context)


def test_terminal_configs_round_trip_through_task_inputs_union() -> None:
    for config in (TerminalAgentConfig(), _make_registered_config()):
        inputs = AgentTaskInputsV2(agent_config=config, git_hash="abc123")
        restored = AgentTaskInputsV2.model_validate_json(inputs.model_dump_json())
        assert restored.agent_config == config
        assert type(restored.agent_config) is type(config)
