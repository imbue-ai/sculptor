"""The harness registry — the one module that names every concrete `Harness`
and every concrete `Agent`. Owns each harness↔agent factory pair so harness
modules do not import agent modules and vice versa. See architecture §1.4–§1.5.

A new harness is added by importing its singleton and its concrete agent
here and adding one `case` branch to each function below.
"""

from __future__ import annotations

from sculptor.agents.default.claude_code_sdk.agent_wrapper import ClaudeCodeSDKAgent
from sculptor.agents.default.claude_code_sdk.harness import CLAUDE_CODE_HARNESS
from sculptor.agents.hello_agent.agent_wrapper import HelloAgent
from sculptor.agents.hello_agent.harness import HELLO_HARNESS
from sculptor.agents.pi_agent.agent_wrapper import PiAgent
from sculptor.agents.pi_agent.harness import PI_HARNESS
from sculptor.foundation.errors import ExpectedError
from sculptor.interfaces.agents.agent import Agent
from sculptor.interfaces.agents.agent import AgentConfigTypes
from sculptor.interfaces.agents.agent import ClaudeCodeSDKAgentConfig
from sculptor.interfaces.agents.agent import HelloAgentConfig
from sculptor.interfaces.agents.agent import PiAgentConfig
from sculptor.interfaces.agents.harness import AgentRunContext
from sculptor.interfaces.agents.harness import Harness
from sculptor.services.workspace_service.setup_command_runner import SetupStateProvider


class UnknownAgentConfigError(ExpectedError):
    """Raised when an `AgentConfigTypes` value has no harness registered for it."""


def get_harness_for_config(config: AgentConfigTypes) -> Harness:
    """Return the `Harness` whose agents construct for the given config.

    The read-side resolver for harness-agnostic consumers that hold a stored
    `agent_config` (e.g. `web/message_conversion.py`, `web/derived.py`).
    See architecture §2.1.
    """
    match config:
        case HelloAgentConfig():
            return HELLO_HARNESS
        case ClaudeCodeSDKAgentConfig():
            return CLAUDE_CODE_HARNESS
        case PiAgentConfig():
            return PI_HARNESS
        case _:
            raise UnknownAgentConfigError(f"Unknown agent config: {config}")


def create_agent_for_run(context: AgentRunContext) -> Agent:
    """Construct the `Agent` for `context.task_data.agent_config`,
    supplying the registry-resolved harness singleton.
    """
    match context.task_data.agent_config:
        case ClaudeCodeSDKAgentConfig() as agent_config:
            setup_state_provider: SetupStateProvider | None = None
            if context.task_state.workspace_id is not None:
                setup_state_provider = context.workspace_service.make_setup_state_provider(
                    str(context.task_state.workspace_id)
                )
            return ClaudeCodeSDKAgent(
                config=agent_config,
                environment=context.environment,
                project=context.project,
                task_id=context.task_id,
                in_testing=context.in_testing,
                system_prompt=context.task_data.system_prompt or "",
                on_diff_needed=context.on_diff_needed,
                workspace_id=context.task_state.workspace_id,
                setup_state_provider=setup_state_provider,
                harness=CLAUDE_CODE_HARNESS,
            )
        case HelloAgentConfig() as agent_config:
            return HelloAgent(
                config=agent_config,
                environment=context.environment,
                task_id=context.task_id,
                system_prompt="",
                on_diff_needed=context.on_diff_needed,
                harness=HELLO_HARNESS,
            )
        case PiAgentConfig() as agent_config:
            return PiAgent(
                config=agent_config,
                environment=context.environment,
                git_hash=context.task_data.git_hash,
                task_id=context.task_id,
                in_testing=context.in_testing,
                system_prompt=context.task_data.system_prompt or "",
                on_diff_needed=context.on_diff_needed,
                harness=PI_HARNESS,
            )
        case _:
            raise UnknownAgentConfigError(f"Unknown agent config: {context.task_data.agent_config}")
