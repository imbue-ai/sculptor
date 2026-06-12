"""Process-wide registry for `/btw` observer queues and subprocess dispatch.

`BtwService` owns the set of per-user WS observer queues that should
receive `BtwUpdate` events and, given a per-task environment, spawns a
`BtwProcessManager` on a background thread to stream the next turn's
answer into every registered queue.
"""

from queue import Full
from queue import Queue
from threading import Lock

from loguru import logger
from pydantic import PrivateAttr

from sculptor.agents.default.claude_code_sdk.btw_process_manager import BtwProcessManager
from sculptor.agents.default.claude_code_sdk.btw_process_manager import NoBtwSessionAvailable
from sculptor.agents.default.claude_code_sdk.harness import CLAUDE_CODE_HARNESS
from sculptor.database.models import TaskID
from sculptor.interfaces.agents.errors import ClaudeBinaryNotFoundError
from sculptor.interfaces.environments.agent_execution_environment import AgentExecutionEnvironment
from sculptor.primitives.ids import WorkspaceID
from sculptor.primitives.service import Service
from sculptor.web.data_types import BtwUpdate
from sculptor.web.data_types import StreamingUpdateSourceTypes


class BtwService(Service):
    """Registry of `/btw` observer queues and subprocess launcher.

    Inherits from ``Service`` so the application's startup/shutdown
    lifecycle owns the threads we spawn for each /btw turn — they are
    started on the injected ``concurrency_group`` and joined when the
    group exits.
    """

    _observer_queues: set[Queue[StreamingUpdateSourceTypes]] = PrivateAttr(default_factory=set)
    _in_flight: dict[TaskID, BtwProcessManager] = PrivateAttr(default_factory=dict)
    _lock: Lock = PrivateAttr(default_factory=Lock)

    def stop(self) -> None:
        """Abort every in-flight /btw subprocess so the concurrency group can join cleanly.

        Without this, ``run_btw`` threads block on ``process.wait()`` and
        the group never exits.
        """
        with self._lock:
            in_flight = list(self._in_flight.values())
        for manager in in_flight:
            manager.abort()

    def add_observer_queue(self, queue: Queue[StreamingUpdateSourceTypes]) -> None:
        with self._lock:
            self._observer_queues.add(queue)

    def remove_observer_queue(self, queue: Queue[StreamingUpdateSourceTypes]) -> None:
        with self._lock:
            self._observer_queues.discard(queue)

    def run_btw_for_task(
        self,
        environment: AgentExecutionEnvironment,
        task_id: TaskID,
        workspace_id: WorkspaceID,
        question: str,
        request_id: str,
        is_fake_claude: bool = False,
        main_agent_started: bool = True,
    ) -> None:
        """Spawn a /btw Haiku turn on a background thread.

        If another /btw is already in-flight for the same agent, SIGTERM it
        first so the popup's "second /btw replaces the first" guarantee
        (architecture §4.4.3) halts the previous subprocess.

        ``main_agent_started`` should be True when the user has sent at
        least one prompt to the main agent (so a session id either exists
        or is imminent). When False, the request fails immediately
        instead of waiting on a session id that will never arrive.

        Raises:
            NoBtwSessionAvailable: the agent has no resumable session yet.
            ClaudeBinaryNotFoundError: the claude binary cannot be resolved.
        """
        manager = BtwProcessManager(
            environment=environment,
            task_id=task_id,
            workspace_id=workspace_id,
            publish=self._publish,
            harness=CLAUDE_CODE_HARNESS,
            is_fake_claude=is_fake_claude,
        )
        # Cold-start race: when the main agent is already running, the user
        # may fire /btw after seeing the thinking indicator but before the
        # main agent's first `system/init` has written the session-id
        # file. Wait briefly to absorb that gap. When the main agent has
        # never been started, no init is coming — fail fast so the user
        # sees the "/btw is unavailable until you've sent a message"
        # toast immediately.
        session_id = manager.wait_for_session_id() if main_agent_started else manager.read_session_id()
        if session_id is None:
            raise NoBtwSessionAvailable(f"Agent {task_id} has no session file to fork from")
        if not is_fake_claude and environment.get_tool_binary_path(CLAUDE_CODE_HARNESS.binary_dependency) is None:
            raise ClaudeBinaryNotFoundError()

        with self._lock:
            previous = self._in_flight.get(task_id)
            self._in_flight[task_id] = manager
        if previous is not None:
            previous.abort()

        # `request_id` is a client-generated UUID v4 (browser
        # `crypto.randomUUID()`), so the leading 8 hex characters are
        # random and yield distinct, human-readable thread names — they
        # are not a timestamp prefix.
        self.concurrency_group.start_new_thread(
            target=self._run_and_clear,
            args=(task_id, manager, question, request_id),
            name=f"btw-{task_id}-{request_id[:8]}",
            is_checked=False,
        )

    def _run_and_clear(self, task_id: TaskID, manager: BtwProcessManager, question: str, request_id: str) -> None:
        try:
            manager.run_btw(question, request_id)
        finally:
            with self._lock:
                # Only clear ourselves out of the map: a newer /btw may have
                # already replaced us, and clobbering its entry would leak its
                # subprocess across the next abort.
                if self._in_flight.get(task_id) is manager:
                    del self._in_flight[task_id]

    def _publish(self, update: BtwUpdate) -> None:
        with self._lock:
            queues = list(self._observer_queues)
        for queue in queues:
            try:
                queue.put_nowait(update)
            except Full:
                logger.warning("Dropping BtwUpdate for request {}: observer queue full", update.request_id)
