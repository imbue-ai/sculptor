import queue
from queue import Empty
from queue import Queue
from threading import Event
from typing import Mapping
from typing import assert_never

from loguru import logger
from pydantic import AnyUrl
from pydantic import PrivateAttr

from sculptor.agents.default.agent_wrapper import DefaultAgentWrapper
from sculptor.foundation.common import generate_id
from sculptor.foundation.secrets_utils import Secret
from sculptor.foundation.thread_utils import ObservableThread
from sculptor.interfaces.agents.agent import FileAgentArtifact
from sculptor.interfaces.agents.agent import HelloAgentConfig
from sculptor.interfaces.agents.agent import StopAgentUserMessage
from sculptor.interfaces.agents.agent import UpdatedArtifactAgentMessage
from sculptor.interfaces.agents.constants import AGENT_EXIT_CODE_CLEAN_SHUTDOWN_ON_INTERRUPT
from sculptor.interfaces.agents.constants import AGENT_EXIT_CODE_SHUTDOWN_DUE_TO_EXCEPTION
from sculptor.interfaces.agents.errors import AgentCrashed
from sculptor.primitives.ids import AgentMessageID
from sculptor.primitives.ids import AssistantMessageID
from sculptor.state.chat_state import TextBlock
from sculptor.state.messages import ChatInputUserMessage
from sculptor.state.messages import ResponseBlockAgentMessage


class HelloAgent(DefaultAgentWrapper):
    config: HelloAgentConfig
    _message_processing_thread: ObservableThread | None = None
    _input_agent_messages: Queue[ChatInputUserMessage] = PrivateAttr(default_factory=Queue)
    _shutdown_event: Event = PrivateAttr(default_factory=Event)

    # pyrefly: ignore [bad-override]
    def push_message(self, message: ChatInputUserMessage | StopAgentUserMessage) -> None:
        match message:
            case ChatInputUserMessage():
                logger.info("Received user input message: {}", message)
                self._input_agent_messages.put(message)
            case StopAgentUserMessage():
                with self._handle_user_message(message):
                    logger.info("Stopping agent")
                    # Mark the turn as stopping so the clean-exit branch of
                    # _handle_user_message suppresses RequestSuccessAgentMessage: an
                    # interrupted turn must not report success.
                    self._is_stopping = True
                    self._shutdown_event.set()
                    self.wait(10.0)
                    self._exit_code = AGENT_EXIT_CODE_CLEAN_SHUTDOWN_ON_INTERRUPT
            case _ as unreachable:
                assert_never(unreachable)

    def poll(self) -> int | None:
        if self._message_processing_thread is not None and self._message_processing_thread.exception_raw is not None:
            self._exception = self._message_processing_thread.exception_raw
            self._exit_code = AGENT_EXIT_CODE_SHUTDOWN_DUE_TO_EXCEPTION
        return super().poll()

    # pyrefly: ignore [bad-override]
    def wait(self, timeout: float) -> int | None:
        if self._exception is not None:
            if self._process is not None:
                self._process.terminate()
            raise AgentCrashed("Agent crashed", exit_code=None, metadata=None) from self._exception
        if self._process is not None:
            exit_code = self._process.wait(30)
            self._exit_code = exit_code
        else:
            exit_code = None

        message_processing_thread = self._message_processing_thread
        assert message_processing_thread is not None
        message_processing_thread.join(30)
        assert not message_processing_thread.is_alive(), "Message processing thread did not finish in time"

        return exit_code

    def terminate(self, force_kill_seconds: float = 5.0) -> None:
        self.wait(timeout=force_kill_seconds)

    def _process_message_queue(self, secrets: Mapping[str, str | Secret]) -> None:
        while not self._shutdown_event.is_set():
            try:
                message = self._input_agent_messages.get(timeout=1)
            except queue.Empty:
                continue
            assert isinstance(message, ChatInputUserMessage)
            with self._handle_user_message(message):
                command = [self.config.command, message.text]
                self._process = self.environment.run_process_in_background(command, secrets=secrets)
                # start the output reader thread -- will add messages to the queue
                self._output_reader()

    def start(
        self,
        secrets: Mapping[str, str | Secret],
    ) -> None:
        self._message_processing_thread = self.concurrency_group.start_new_thread(
            target=self._process_message_queue, args=(secrets,)
        )

    def _create_artifact_message(
        self, content: str, assistant_message_id: AssistantMessageID
    ) -> UpdatedArtifactAgentMessage:
        """Create an artifact message with the given content."""
        path = f"/tmp/artifacts/hello_output_{assistant_message_id}.txt"
        self.environment.write_file(path, content)
        artifact = FileAgentArtifact(
            name=path,
            url=AnyUrl(f"file://{path}"),
        )
        return UpdatedArtifactAgentMessage(
            message_id=AgentMessageID(),
            artifact=artifact,
        )

    def _output_reader(self) -> None:
        process = self._process
        assert process is not None
        queue = process.get_queue()
        while not process.is_finished() or not queue.empty():
            try:
                line, is_stdout = queue.get(timeout=0.1)
            except Empty:
                continue
            if not is_stdout:
                continue
            assistant_message_id = AssistantMessageID(generate_id())
            content = line.strip()

            response_block_message = ResponseBlockAgentMessage(
                message_id=AgentMessageID(),
                role="assistant",
                assistant_message_id=assistant_message_id,
                content=(TextBlock(text=content),),
            )
            self._output_messages.put(response_block_message)

            artifact_message = self._create_artifact_message(content, assistant_message_id)
            self._output_messages.put(artifact_message)
