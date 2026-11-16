"""A Claude chat agent in a jj workspace, run against FakeClaude, is told to use the jj skill.

FakeClaude echoes the system prompt it was launched with and the prompt each
turn carries, so the assertions read what the agent was actually told.
"""

import contextlib
from collections.abc import Iterator
from queue import Queue

import pytest

from sculptor.agents.default.claude_code_sdk.harness import CLAUDE_CODE_HARNESS
from sculptor.agents.default.claude_code_sdk.process_manager import ClaudeProcessManager
from sculptor.agents.testing.fake_claude import ECHO_PROMPTS_ENV_VAR
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.interfaces.agents.agent import ClearContextUserMessage
from sculptor.primitives.ids import TaskID
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.workspace_service.environment_manager.environments.local_agent_execution_environment import (
    LocalAgentExecutionEnvironment,
)
from sculptor.services.workspace_service.jj_bookmark_facts import JjBookmarkFacts
from sculptor.state.chat_state import TextBlock
from sculptor.state.messages import ChatInputUserMessage
from sculptor.state.messages import LLMModel
from sculptor.state.messages import Message
from sculptor.state.messages import ResponseBlockAgentMessage
from sculptor.testing.jj_launch_environment import JjLaunchEnvironment
from sculptor.testing.jj_launch_environment import jj_environment_nested_in_git_repository  # noqa: F401
from sculptor.testing.sculptor_folder import isolated_sculptor_folder  # noqa: F401

_TURN_TIMEOUT_SECONDS = 60.0
_STOP_TIMEOUT_SECONDS = 10.0
_JJ_SKILL_REMINDER = 'invoke the `sculptor-jj:jujutsu` skill with the Skill tool (skill="sculptor-jj:jujutsu")'
_JJ_SKILL_RULE = "The `sculptor-jj:jujutsu` skill is required for version control in this workspace."
_BOOKMARK_REMINDER = "Sculptor names this workspace's work with the jj bookmark `dev/graph-view`."


class _StaticJjBookmarkFacts:
    def __init__(self, facts: JjBookmarkFacts) -> None:
        self._facts = facts

    def get_jj_bookmark_facts(self) -> JjBookmarkFacts:
        return self._facts


@pytest.fixture
def jj_claude_process_manager(
    jj_environment_nested_in_git_repository: JjLaunchEnvironment,  # noqa: F811
    test_root_concurrency_group: ConcurrencyGroup,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[ClaudeProcessManager]:
    monkeypatch.setenv(ECHO_PROMPTS_ENV_VAR, "1")
    agent_environment = LocalAgentExecutionEnvironment(
        jj_environment_nested_in_git_repository.environment,
        TaskID(),
        DependencyManagementService(concurrency_group=test_root_concurrency_group),
    )
    process_manager = ClaudeProcessManager(
        environment=agent_environment,
        task_id=TaskID(),
        in_testing=True,
        secrets={},
        output_message_queue=Queue(),
        handle_user_message_callback=lambda message: contextlib.nullcontext(),
        system_prompt="",
        harness=CLAUDE_CODE_HARNESS,
        jj_bookmark_facts_provider=_StaticJjBookmarkFacts(
            JjBookmarkFacts(requested_bookmark="dev/graph-view", stack=None)
        ),
    )
    try:
        yield process_manager
    finally:
        process_manager.stop(_STOP_TIMEOUT_SECONDS, is_waiting=True)


def _run_turn(process_manager: ClaudeProcessManager, text: str) -> str:
    """Send one chat message and return the text FakeClaude answered with."""
    process_manager.process_input_message(ChatInputUserMessage(text=text, model_name=LLMModel.FAKE_CLAUDE))
    _wait_for_message_processing(process_manager)
    return "\n".join(_drain_text_blocks(process_manager._output_messages))


def _clear_context(process_manager: ClaudeProcessManager) -> None:
    process_manager.process_clear_context_message(ClearContextUserMessage())
    _wait_for_message_processing(process_manager)


def _wait_for_message_processing(process_manager: ClaudeProcessManager) -> None:
    thread = process_manager._message_processing_thread
    assert thread is not None
    thread.join(timeout=_TURN_TIMEOUT_SECONDS)
    assert not thread.is_alive(), "the process manager did not finish handling the message"


def _drain_text_blocks(messages: "Queue[Message]") -> list[str]:
    texts: list[str] = []
    while not messages.empty():
        message = messages.get_nowait()
        if isinstance(message, ResponseBlockAgentMessage):
            texts.extend(block.text for block in message.content if isinstance(block, TextBlock))
    return texts


def test_a_jj_workspace_agent_is_told_on_its_first_turn_to_invoke_the_jj_skill(
    jj_claude_process_manager: ClaudeProcessManager,
) -> None:
    echo = _run_turn(jj_claude_process_manager, "hello")

    system_prompt, _, prompt = echo.partition("[FakeClaude] prompt:\n")
    assert _JJ_SKILL_RULE in system_prompt
    assert "jj workspace mode" in system_prompt
    assert prompt.startswith("<system-reminder>\nThis is a jj (Jujutsu) workspace.")
    assert _JJ_SKILL_REMINDER in prompt
    assert _BOOKMARK_REMINDER in prompt
    assert prompt.rstrip().endswith("hello")


def test_a_jj_workspace_agent_is_told_again_after_its_context_is_cleared_but_not_on_later_turns(
    jj_claude_process_manager: ClaudeProcessManager,
) -> None:
    _run_turn(jj_claude_process_manager, "first")
    second_echo = _run_turn(jj_claude_process_manager, "second")
    _clear_context(jj_claude_process_manager)
    after_clear_echo = _run_turn(jj_claude_process_manager, "after clear")

    second_system_prompt, _, second_prompt = second_echo.partition("[FakeClaude] prompt:\n")
    assert _JJ_SKILL_RULE in second_system_prompt
    assert _JJ_SKILL_REMINDER not in second_prompt
    assert _BOOKMARK_REMINDER not in second_prompt
    assert _JJ_SKILL_REMINDER in after_clear_echo
