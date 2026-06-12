"""Uses the Anthropic Claude Code SDK to run a Claude Code agent.

Particularly, headless mode: https://docs.anthropic.com/en/docs/claude-code/sdk/sdk-headless
"""

from __future__ import annotations

from loguru import logger
from pydantic import PrivateAttr

from sculptor.agents.default.agent_wrapper import DefaultAgentWrapper
from sculptor.agents.default.claude_code_sdk.harness import ClaudeCodeHarness
from sculptor.agents.default.claude_code_sdk.process_manager import ClaudeProcessManager
from sculptor.database.models import Project
from sculptor.interfaces.agents.agent import ClaudeCodeSDKAgentConfig
from sculptor.interfaces.agents.agent import ClearContextUserMessage
from sculptor.interfaces.agents.agent import InterruptProcessUserMessage
from sculptor.interfaces.agents.agent import RequestSkippedAgentMessage
from sculptor.interfaces.agents.agent import ResumeAgentResponseRunnerMessage
from sculptor.interfaces.agents.agent import UserQuestionAnswerMessage
from sculptor.interfaces.agents.constants import AGENT_EXIT_CODE_SHUTDOWN_DUE_TO_EXCEPTION
from sculptor.primitives.ids import WorkspaceID
from sculptor.services.workspace_service.setup_command_runner import SetupStateProvider
from sculptor.state.messages import ChatInputUserMessage
from sculptor.state.messages import Message


class ClaudeCodeSDKAgent(DefaultAgentWrapper):
    # Narrows the inherited `harness: Harness` field. The narrow is safe
    # because the registry (`harness_registry.create_agent_for_run`) owns
    # construction — so the concrete harness module never imports this
    # agent module, and no import cycle exists.
    harness: ClaudeCodeHarness
    config: ClaudeCodeSDKAgentConfig
    project: Project
    workspace_id: WorkspaceID | None = None
    setup_state_provider: SetupStateProvider | None = None
    _claude_process_manager: ClaudeProcessManager | None = PrivateAttr(default=None)

    def _terminate(self, force_kill_seconds: float = 5.0) -> None:
        assert self._claude_process_manager is not None, "Claude process manager must be set"
        self._claude_process_manager.stop(force_kill_seconds, is_waiting=False)

    def poll(self) -> int | None:
        assert self._claude_process_manager is not None, "Claude process manager must be set"
        if self._claude_process_manager.get_exception_if_exists() is not None:
            self._exit_code = AGENT_EXIT_CODE_SHUTDOWN_DUE_TO_EXCEPTION
        return super().poll()

    def wait(self, timeout: float) -> int:
        assert self._claude_process_manager is not None, "Claude process manager must be set"
        self._claude_process_manager.stop(timeout, is_waiting=True)

        assert self._exit_code is not None, (
            "The wait method will only ever terminate if the agent is stopped or if there is an exception"
        )
        return self._exit_code

    def _start(self) -> None:
        self._claude_process_manager = ClaudeProcessManager(
            environment=self.environment,
            in_testing=self.in_testing,
            secrets=self._secrets,
            task_id=self.task_id,
            output_message_queue=self._output_messages,
            handle_user_message_callback=self._handle_user_message,
            system_prompt=self.system_prompt,
            harness=self.harness,
            on_diff_needed=self.on_diff_needed,
            workspace_id=self.workspace_id,
            setup_state_provider=self.setup_state_provider,
        )

    def _push_message(self, message: Message) -> bool:
        match message:
            case ChatInputUserMessage() | ResumeAgentResponseRunnerMessage() | UserQuestionAnswerMessage():
                if message.message_id.suffix in self._removed_message_ids:
                    logger.info("Skipping message {} as it has been removed", message.message_id)
                    self._output_messages.put(RequestSkippedAgentMessage(request_id=message.message_id))
                else:
                    assert self._claude_process_manager is not None, "Claude process manager must be set"
                    self._claude_process_manager.process_input_message(message=message)
            case ClearContextUserMessage():
                assert self._claude_process_manager is not None, "Claude process manager must be set"
                self._claude_process_manager.process_clear_context_message(message=message)
            case InterruptProcessUserMessage():
                assert self._claude_process_manager is not None, "Claude process manager must be set"
                # Set the interrupted flag BEFORE calling interrupt_current_message,
                # because interrupt_current_message joins the message-processing thread
                # which reads this flag in its completion handler.
                process_manager = self._claude_process_manager
                self._was_interrupted.set()
                process_manager.interrupt_current_message(message=message)
            case _:
                return False
        return True
