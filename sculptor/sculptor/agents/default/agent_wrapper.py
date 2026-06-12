from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from queue import Queue
from typing import Callable
from typing import Generator
from typing import Mapping

from loguru import logger
from pydantic import PrivateAttr

from imbue_core.agents.data_types.ids import AgentMessageID
from imbue_core.agents.data_types.ids import TaskID
from imbue_core.async_monkey_patches import log_exception
from imbue_core.concurrency_group import ConcurrencyGroup
from imbue_core.constants import ExceptionPriority
from imbue_core.processes.local_process import RunningProcess
from imbue_core.sculptor.state.messages import Message
from imbue_core.secrets_utils import Secret
from sculptor.agents.default.constants import DEFAULT_WAIT_TIMEOUT
from sculptor.agents.default.constants import REMOVED_MESSAGE_IDS_STATE_FILE
from sculptor.agents.default.utils import get_state_file_contents
from sculptor.agents.default.utils import get_turn_request_id
from sculptor.agents.default.utils import serialize_agent_wrapper_error
from sculptor.interfaces.agents.agent import Agent
from sculptor.interfaces.agents.agent import MessageTypes
from sculptor.interfaces.agents.agent import RemoveQueuedMessageAgentMessage
from sculptor.interfaces.agents.agent import RemoveQueuedMessageUserMessage
from sculptor.interfaces.agents.agent import RequestStartedAgentMessage
from sculptor.interfaces.agents.agent import RequestSuccessAgentMessage
from sculptor.interfaces.agents.agent import ResumeAgentResponseRunnerMessage
from sculptor.interfaces.agents.agent import StopAgentUserMessage
from sculptor.interfaces.agents.agent import UserMessageUnion
from sculptor.interfaces.agents.constants import AGENT_EXIT_CODE_CLEAN_SHUTDOWN_ON_INTERRUPT
from sculptor.interfaces.agents.constants import AGENT_EXIT_CODE_FROM_SIGINT
from sculptor.interfaces.agents.constants import AGENT_EXIT_CODE_FROM_SIGTERM
from sculptor.interfaces.agents.constants import SIGINT_EXIT_CODES
from sculptor.interfaces.agents.constants import SIGTERM_EXIT_CODES
from sculptor.interfaces.agents.errors import AgentClientError
from sculptor.interfaces.agents.errors import AgentTransientError
from sculptor.interfaces.agents.harness import Harness
from sculptor.interfaces.environments.agent_execution_environment import AgentExecutionEnvironment


class DefaultAgentWrapper(Agent):
    """
    The default class for all AgentWrappers. Holds common logic and fields between all agents and interacts with
    the agent runner to manage the inner agent.
    """

    harness: Harness
    environment: AgentExecutionEnvironment
    task_id: TaskID
    in_testing: bool = False
    _removed_message_ids: set[str] = PrivateAttr(default_factory=set)
    _secrets: dict[str, str | Secret] = PrivateAttr(default_factory=dict)
    _output_messages: Queue[Message] = PrivateAttr(default_factory=Queue)
    _exception: BaseException | None = PrivateAttr(default=None)
    _process: RunningProcess | None = PrivateAttr(default=None)
    _exit_code: int | None = PrivateAttr(default=None)
    _is_stopping: bool = PrivateAttr(default=False)
    _was_interrupted: threading.Event = PrivateAttr(default_factory=threading.Event)

    system_prompt: str
    on_diff_needed: Callable[[], None] | None = None

    def start(
        self,
        secrets: Mapping[str, str | Secret],
    ) -> None:
        # Load secrets
        self._secrets = dict(secrets)

        self._removed_message_ids = set(
            json.loads(get_state_file_contents(self.environment, REMOVED_MESSAGE_IDS_STATE_FILE) or "[]")
        )

        # Workspace diff is NOT refreshed here. The caller (v1.py) signals the
        # frontend via mark_workspace_diff_stale, and the actual artifact is
        # generated on-demand when the frontend fetches the diff endpoint.
        # The on_diff_needed callback is still used later when the agent modifies files.

        # Perform any agent-specific initialization
        self._start()

    def pop_messages(self) -> list[MessageTypes]:
        new_logs = []
        while self._output_messages.qsize() > 0:
            message = self._output_messages.get_nowait()
            new_logs.append(message)
        # pyrefly: ignore [bad-return]
        return new_logs

    def push_message(self, message: Message) -> None:
        # Perform agent-specific message handling
        is_message_handled = self._push_message(message=message)
        if is_message_handled:
            return
        # If the message is not handled by the agent-specific message handling, perform generic handling
        # This is to prevent a message from being handled twice, which would split the message-handling logic
        match message:
            case RemoveQueuedMessageUserMessage():
                with self._handle_user_message(message):
                    self._removed_message_ids.add(message.target_message_id.suffix)
                    self.environment.write_file(
                        str(self.environment.get_state_path() / REMOVED_MESSAGE_IDS_STATE_FILE),
                        json.dumps(list(self._removed_message_ids)),
                    )
                    logger.info("Removed message id: {}", message.target_message_id)
                    self._output_messages.put(
                        RemoveQueuedMessageAgentMessage(removed_message_id=message.target_message_id)
                    )
            case StopAgentUserMessage():
                logger.info("Stopping agent")
                with self._handle_user_message(message):
                    self.terminate(DEFAULT_WAIT_TIMEOUT)
                    self._exit_code = AGENT_EXIT_CODE_CLEAN_SHUTDOWN_ON_INTERRUPT
                logger.info("Finished stopping agent")

    def poll(self) -> int | None:
        return self._exit_code

    def terminate(self, force_kill_seconds: float = 5.0) -> None:
        self.environment.stop_terminal_manager()
        self._terminate(force_kill_seconds=force_kill_seconds)

    def _start(self) -> None: ...

    def _push_message(self, message: Message) -> bool:
        return False

    def _terminate(self, force_kill_seconds: float) -> None: ...

    @property
    def concurrency_group(self) -> ConcurrencyGroup:
        return self.environment.concurrency_group

    @contextmanager
    def _handle_user_message(
        self, message: UserMessageUnion | ResumeAgentResponseRunnerMessage
    ) -> Generator[None, None, None]:
        # A resumed turn must report the id of the turn it continues
        # (for_user_message_id), not the resume message's own id, so its
        # completion matches the original chat message. See get_turn_request_id.
        request_id = get_turn_request_id(message)
        self._output_messages.put(
            RequestStartedAgentMessage(
                message_id=AgentMessageID(),
                request_id=request_id,
            )
        )
        try:
            yield
        # if it is a claude client error, let's report it and allow the user to retry or continue
        # otherwise, let's raise it out of the agent wrapper to be handled by the caller
        except AgentClientError as e:
            # if we got a sigterm, it's likely because we are shutting down in tests, so, probably worth bailing
            # also in this case it doesn't matter what kind of AgentClientError it is
            if e.exit_code in SIGTERM_EXIT_CODES:
                is_stopping = True
                self._exit_code = AGENT_EXIT_CODE_FROM_SIGTERM
                logger.info("Received SIGTERM, likely due to shutdown, no need to log further")
            elif e.exit_code in SIGINT_EXIT_CODES:
                is_stopping = True
                self._exit_code = AGENT_EXIT_CODE_FROM_SIGINT
                logger.info("Received SIGINT, likely due to controlled shutdown, no need to log further")
            # if it wasn't a shutdown, we need to know if it was transient (and hence expected),
            # in which case we stop quietly rather than treating it as a failure
            elif isinstance(e, AgentTransientError):
                is_stopping = False
            else:
                is_stopping = False
                log_exception(
                    e,
                    "Non-transient AgentClientError with exit code {exit_code} handling user message '{user_message}'",
                    exit_code=e.exit_code,
                    user_message=message,
                    # Lower priority of transient LLM API errors
                    priority=ExceptionPriority.LOW_PRIORITY,
                )
            self._output_messages.put(serialize_agent_wrapper_error(e=e, message=message, is_stopping=is_stopping))
        except Exception as e:
            log_exception(
                e,
                "Error handling user message: {user_message}",
                user_message=message,
            )
            self._output_messages.put(serialize_agent_wrapper_error(e=e, message=message, is_stopping=False))
            # since it's not a claude client error, raise it out of the agent wrapper
            raise
        else:
            # no errors
            if not self._is_stopping:
                was_interrupted = self._was_interrupted.is_set()
                self._was_interrupted.clear()
                self._output_messages.put(
                    RequestSuccessAgentMessage(
                        message_id=AgentMessageID(),
                        request_id=request_id,
                        error=None,
                        interrupted=was_interrupted,
                    )
                )
