import time
from threading import Event
from typing import Mapping
from typing import assert_never

from loguru import logger
from pydantic import PrivateAttr

from imbue_core.agents.data_types.ids import AgentMessageID
from imbue_core.common import generate_id
from imbue_core.thread_utils import ObservableThread
from sculptor.interfaces.agents.v1.agent import AGENT_EXIT_CODE_CLEAN_SHUTDOWN_ON_INTERRUPT
from sculptor.interfaces.agents.v1.agent import AGENT_EXIT_CODE_SHUTDOWN_DUE_TO_EXCEPTION
from sculptor.interfaces.agents.v1.agent import ClaudeCodeTextAgentConfig
from sculptor.interfaces.agents.v1.agent import ErrorType
from sculptor.interfaces.agents.v1.agent import ProcessWrapperAgent
from sculptor.interfaces.agents.v1.agent import ServerReadyAgentMessage
from sculptor.interfaces.agents.v1.agent import StopAgentUserMessage
from sculptor.interfaces.agents.v1.agent import UserMessage
from sculptor.interfaces.agents.v1.errors import AgentCrashed
from sculptor.interfaces.environments.v1.base import TTYD_SERVER_NAME
from sculptor.utils.secret import Secret


class ClaudeCodeTextAgent(ProcessWrapperAgent):
    config: ClaudeCodeTextAgentConfig
    _monitor_thread: ObservableThread | None = None
    _tmux_session_name: str = PrivateAttr(default_factory=generate_id)
    _shutdown_event: Event = PrivateAttr(default_factory=Event)

    def push_message(self, message: UserMessage) -> None:
        match message:
            case StopAgentUserMessage():
                with self._handle_user_message(message):
                    logger.info("Stopping text agent")
                    self._shutdown_event.set()
                    if self._process is not None:
                        self._process.terminate()
                    monitor_thread = self._monitor_thread
                    if monitor_thread is not None:
                        monitor_thread.join(timeout=10)
                        if monitor_thread.is_alive():
                            logger.info("Monitor thread did not terminate cleanly")
                    # Clean up tmux session
                    try:
                        cleanup_process = self.environment.run_process_in_background(
                            ["tmux", "kill-session", "-t", self._tmux_session_name], secrets={}
                        )
                        cleanup_process.wait()
                    except Exception as e:
                        logger.debug("Error cleaning up tmux session: {}", e)
                    self._exit_code = AGENT_EXIT_CODE_CLEAN_SHUTDOWN_ON_INTERRUPT
            case _ as unreachable:
                # pyre-fixme[6]: Change message to have a proper union type (instead of a base class that can have an unbound amount of subclasses), and handle other possible types here.
                assert_never(unreachable)

    def poll(self) -> int | None:
        if self._monitor_thread is not None and self._monitor_thread.exception is not None:
            self._exception = self._monitor_thread.exception
            self._exit_code = AGENT_EXIT_CODE_SHUTDOWN_DUE_TO_EXCEPTION
        return super().poll()

    # TODO: cleanup this waiting / shutdown / timeout logic here to conform to the docstring (see timeout below)
    def wait(self, timeout: float) -> int:
        if self._exception is not None:
            if self._process is not None:
                self._process.terminate(timeout)
            raise AgentCrashed("Agent crashed", exit_code=None, metadata=None) from self._exception

        process = self._process
        assert process is not None
        exit_code = process.wait(timeout)
        self._exit_code = exit_code

        # Properly handle thread pool shutdown and bubble up exceptions
        monitor_thread = self._monitor_thread
        if monitor_thread is not None:
            self._shutdown_event.set()
            monitor_thread.join(timeout=10)
            if monitor_thread.is_alive():
                logger.info("Monitor thread did not terminate cleanly")
        self._cleanup_tmux_session()

        return exit_code

    def _on_start(self, secrets: Mapping[str, str | Secret]) -> None:
        logger.info("Starting claude under tmux")
        claude_command = ["tmux", "new-session", "-d", "-s", self._tmux_session_name, "claude"]
        if self.config.initial_prompt:
            claude_command.append(self.config.initial_prompt)

        claude_tmux_process = self.environment.run_process_in_background(claude_command, secrets=secrets)
        exit_code = claude_tmux_process.wait()

        if exit_code != 0:
            stderr = claude_tmux_process.read_stderr()
            logger.error("Failed to create tmux session, exit code: {} stderr: {}", exit_code, stderr)
            raise AgentCrashed(
                f"Agent died with exit code {exit_code}",
                exit_code=exit_code,
                metadata={
                    "source_command": " ".join(claude_command),
                    "error": ErrorType.NONZERO_EXIT_CODE,
                    "stderr": stderr,
                },
            )

        terminal_port = self.environment.get_config().server_port_by_name.get(TTYD_SERVER_NAME, 0)
        logger.info("Starting ttyd. Punchthrough port is {}. Check your browser", terminal_port)
        ttyd_command = [
            "ttyd",
            "-p",
            str(terminal_port),
            "-W",
            "-o",
            "tmux",
            "a",
            "-t",
            self._tmux_session_name,
        ]  # FIXME: without opening a pty and redirecting stdin, ttyd will make the log outputs weirdly formatted and garbled
        ttyd_process = self.environment.run_process_in_background(ttyd_command, secrets=secrets)
        ttyd_url = self.environment.get_server_url("FIXME")
        self._output_messages.put(ServerReadyAgentMessage(url=ttyd_url, message_id=AgentMessageID(), name="FIXME"))
        self._process = ttyd_process

        # Start monitoring both ttyd and tmux session with proper exception handling
        self._monitor_thread = ObservableThread(target=self._monitor_processes, args=(" ".join(ttyd_command),))
        self._monitor_thread.start()

    def _monitor_processes(self, source_command: str) -> None:
        """Monitor both ttyd process and tmux session health"""
        exit_code = None
        while not self._shutdown_event.is_set():
            # Check ttyd process
            process = self._process
            if process:
                exit_code = process.poll()
                if exit_code is not None:
                    logger.error("ttyd process died with exit code: {}", exit_code)
                    raise AgentCrashed(
                        f"Agent died with exit code {exit_code}",
                        exit_code=exit_code,
                        metadata={
                            "source_command": " ".join(source_command),
                            "error": ErrorType.NONZERO_EXIT_CODE,
                            "stderr": process.read_stderr(),
                        },
                    )

            if not self._is_tmux_session_alive():
                logger.error("tmux session '{}' no longer exists", self._tmux_session_name)
                raise AgentCrashed(
                    f"Agent died with exit code {exit_code}",
                    exit_code=exit_code,
                    metadata={
                        "source_command": " ".join(source_command),
                        "error": ErrorType.TMUX_SESSION_DIED,
                    },
                )
            time.sleep(5)

    def _is_tmux_session_alive(self) -> bool:
        """Check if the tmux session still exists"""
        try:
            check_process = self.environment.run_process_in_background(
                ["tmux", "has-session", "-t", self._tmux_session_name], secrets={}
            )
            return check_process.wait() == 0
        except Exception as e:
            logger.debug("Error checking tmux session: {}", e)
            return False

    def _cleanup_tmux_session(self) -> None:
        """Clean up the tmux session"""
        try:
            cleanup_process = self.environment.run_process_in_background(
                ["tmux", "kill-session", "-t", self._tmux_session_name], secrets={}
            )
            cleanup_process.wait()
            logger.info("Cleaned up tmux session: {}", self._tmux_session_name)
        except Exception as e:
            logger.debug("Error cleaning up tmux session: {}", e)
