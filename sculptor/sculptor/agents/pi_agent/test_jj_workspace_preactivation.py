"""A pi agent in a jj workspace, run against FakePi, invokes the jj skill on its first turn.

FakePi answers a `/skill:<name>` prompt that carries no directive by naming the
skill it followed, so the assertions read which skill pi was asked to load.
"""

from collections.abc import Iterator
from pathlib import Path
from queue import Empty

import pytest

from sculptor.agents.pi_agent.agent_wrapper import PiAgent
from sculptor.agents.pi_agent.harness import PI_HARNESS
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.interfaces.agents.agent import ClearContextUserMessage
from sculptor.interfaces.agents.agent import PiAgentConfig
from sculptor.interfaces.agents.agent import RequestSuccessAgentMessage
from sculptor.primitives.ids import AgentMessageID
from sculptor.primitives.ids import TaskID
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.user_config.user_config import get_user_config_instance
from sculptor.services.user_config.user_config import set_user_config_instance
from sculptor.services.workspace_service.environment_manager.environments.local_agent_execution_environment import (
    LocalAgentExecutionEnvironment,
)
from sculptor.services.workspace_service.jj_bookmark_facts import JjBookmarkFacts
from sculptor.state.chat_state import TextBlock
from sculptor.state.messages import ChatInputUserMessage
from sculptor.state.messages import ResponseBlockAgentMessage
from sculptor.testing.fake_pi import install_fake_pi_binary
from sculptor.testing.jj_launch_environment import JjLaunchEnvironment
from sculptor.testing.jj_launch_environment import jj_environment_nested_in_git_repository  # noqa: F401
from sculptor.testing.sculptor_folder import isolated_sculptor_folder  # noqa: F401

_TURN_TIMEOUT_SECONDS = 30.0
_STOP_TIMEOUT_SECONDS = 10.0
_FOLLOWED_JJ_SKILL = "[FakePi] followed skill: jujutsu"
_FOLLOWED_NO_SKILL = "[FakePi] Task completed."


class _StaticJjBookmarkFacts:
    def __init__(self, facts: JjBookmarkFacts) -> None:
        self._facts = facts

    def get_jj_bookmark_facts(self) -> JjBookmarkFacts:
        return self._facts


def _make_pi_agent(launch: JjLaunchEnvironment, concurrency_group: ConcurrencyGroup, task_id: TaskID) -> PiAgent:
    return PiAgent(
        harness=PI_HARNESS,
        environment=LocalAgentExecutionEnvironment(
            launch.environment, task_id, DependencyManagementService(concurrency_group=concurrency_group)
        ),
        task_id=task_id,
        config=PiAgentConfig(),
        system_prompt="",
        git_hash="deadbeef",
        jj_bookmark_facts_provider=_StaticJjBookmarkFacts(
            JjBookmarkFacts(requested_bookmark="dev/graph-view", stack=None)
        ),
    )


@pytest.fixture
def jj_pi_agent(
    jj_environment_nested_in_git_repository: JjLaunchEnvironment,  # noqa: F811
    test_root_concurrency_group: ConcurrencyGroup,
    tmp_path: Path,
) -> Iterator[PiAgent]:
    fake_bin_dir = tmp_path / "fake_pi_bin"
    fake_bin_dir.mkdir()
    fake_pi = install_fake_pi_binary(fake_bin_dir)
    config = get_user_config_instance()
    set_user_config_instance(
        config.model_copy(update={"dependency_paths": config.dependency_paths.model_copy(update={"pi": str(fake_pi)})})
    )
    agent = _make_pi_agent(jj_environment_nested_in_git_repository, test_root_concurrency_group, TaskID())
    agent.start(secrets={})
    try:
        yield agent
    finally:
        agent.wait(_STOP_TIMEOUT_SECONDS)


def _run_turn(agent: PiAgent, text: str) -> str:
    """Send one chat message and return the text FakePi answered with."""
    message = ChatInputUserMessage(text=text)
    agent.push_message(message)
    return "\n".join(_wait_for_request_texts(agent, message.message_id))


def _clear_context(agent: PiAgent) -> None:
    message = ClearContextUserMessage(message_id=AgentMessageID())
    agent.push_message(message)
    _wait_for_request_texts(agent, message.message_id)


def _wait_for_request_texts(agent: PiAgent, request_id: AgentMessageID) -> list[str]:
    texts: list[str] = []
    while True:
        try:
            message = agent._output_messages.get(timeout=_TURN_TIMEOUT_SECONDS)
        except Empty:
            raise AssertionError(f"request {request_id} did not complete") from None
        if isinstance(message, ResponseBlockAgentMessage):
            texts.extend(block.text for block in message.content if isinstance(block, TextBlock))
        if isinstance(message, RequestSuccessAgentMessage) and message.request_id == request_id:
            return texts


def test_a_jj_workspace_pi_agent_invokes_the_jj_skill_on_its_first_turn_only(jj_pi_agent: PiAgent) -> None:
    first_turn = _run_turn(jj_pi_agent, "hello")
    second_turn = _run_turn(jj_pi_agent, "hello again")

    assert _FOLLOWED_JJ_SKILL in first_turn
    assert _FOLLOWED_NO_SKILL in second_turn


def test_a_jj_workspace_pi_agent_invokes_the_jj_skill_again_after_its_context_is_cleared(
    jj_pi_agent: PiAgent,
) -> None:
    _run_turn(jj_pi_agent, "hello")
    _clear_context(jj_pi_agent)
    after_clear = _run_turn(jj_pi_agent, "hello after clear")

    assert _FOLLOWED_JJ_SKILL in after_clear


def test_a_jj_workspace_pi_agent_resumed_after_its_first_turn_does_not_invoke_the_jj_skill_again(
    jj_environment_nested_in_git_repository: JjLaunchEnvironment,  # noqa: F811
    jj_pi_agent: PiAgent,
    test_root_concurrency_group: ConcurrencyGroup,
) -> None:
    _run_turn(jj_pi_agent, "hello")
    jj_pi_agent.wait(_STOP_TIMEOUT_SECONDS)
    resumed_agent = _make_pi_agent(
        jj_environment_nested_in_git_repository, test_root_concurrency_group, jj_pi_agent.task_id
    )
    resumed_agent.start(secrets={})
    try:
        after_resume = _run_turn(resumed_agent, "hello after resume")
    finally:
        resumed_agent.wait(_STOP_TIMEOUT_SECONDS)

    assert _FOLLOWED_NO_SKILL in after_resume


def test_a_skill_the_user_invokes_on_the_first_turn_goes_first_and_the_jj_skill_follows_on_the_next(
    jj_pi_agent: PiAgent,
) -> None:
    first_turn = _run_turn(jj_pi_agent, "/sculptor-workflow:fix-bug the login loop")
    second_turn = _run_turn(jj_pi_agent, "hello")

    assert "[FakePi] followed skill: fix-bug" in first_turn
    assert _FOLLOWED_JJ_SKILL in second_turn


def test_a_jj_workspace_pi_agent_is_told_the_jj_skill_is_required_and_which_bookmark_names_its_work(
    jj_pi_agent: PiAgent,
) -> None:
    system_prompt = jj_pi_agent._build_system_prompt()

    assert "The `jujutsu` skill is required for version control in this workspace." in system_prompt
    assert "Sculptor names this workspace's work with the jj bookmark `dev/graph-view`." in system_prompt
