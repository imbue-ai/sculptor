import os
from queue import Queue
from typing import Callable
from typing import Generator
from typing import TypeVar

import pytest

from imbue_core.agents.data_types.ids import AgentMessageID
from imbue_core.itertools import only
from imbue_core.sculptor.state.messages import ChatInputUserMessage
from imbue_core.sculptor.state.messages import Message
from imbue_core.test_utils import wait_until
from imbue_core.thread_utils import ObservableThread
from sculptor.database.models import AgentTaskInputsV1
from sculptor.database.models import AgentTaskStateV1
from sculptor.database.models import Project
from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.interfaces.agents.v1.agent import AgentSnapshotRunnerMessage
from sculptor.interfaces.agents.v1.agent import CheckFinishedReason
from sculptor.interfaces.agents.v1.agent import CheckFinishedRunnerMessage
from sculptor.interfaces.agents.v1.agent import CheckLaunchedRunnerMessage
from sculptor.interfaces.agents.v1.agent import ChecksDefinedRunnerMessage
from sculptor.interfaces.agents.v1.agent import NewSuggestionRunnerMessage
from sculptor.interfaces.agents.v1.agent import RequestStartedAgentMessage
from sculptor.interfaces.agents.v1.agent import RequestSuccessAgentMessage
from sculptor.interfaces.agents.v1.agent import RestartCheckUserMessage
from sculptor.interfaces.agents.v1.agent import StopAgentUserMessage
from sculptor.interfaces.agents.v1.agent import StopCheckUserMessage
from sculptor.interfaces.agents.v1.agent import TaskState
from sculptor.services.environment_service.environments.local_environment import LocalEnvironment
from sculptor.services.task_service.data_types import ServiceCollectionForTask
from sculptor.tasks.handlers.run_agent.checks.constants import CHECK_CONFIG_PATH
from sculptor.tasks.handlers.run_agent.checks.constants import SCULPTOR_SYSTEM_CHECK_NAME
from sculptor.tasks.handlers.run_agent.conftest import get_all_messages_for_task
from sculptor.tasks.handlers.run_agent.v1 import AgentShutdownCleanly
from sculptor.tasks.handlers.run_agent.v1 import _run_agent_in_environment

if os.environ.get("IMBUE_MODAL_INTEGRATION_TEST", "False").lower() in ("true", "1", "t"):
    _THREAD_TIMEOUT = 10.0
else:
    _THREAD_TIMEOUT = 30.0


@pytest.fixture
def local_task_state(local_task: Task) -> AgentTaskStateV1:
    return AgentTaskStateV1()


@pytest.fixture
def input_message_queue() -> Queue[Message]:
    return Queue()


@pytest.fixture
def task_thread(
    local_task: Task,
    local_task_state: AgentTaskStateV1,
    environment: LocalEnvironment,
    services: ServiceCollectionForTask,
    project: Project,
    input_message_queue: Queue[Message],
) -> ObservableThread:
    return _create_task_thread(
        local_task=local_task,
        local_task_state=local_task_state,
        environment=environment,
        services=services,
        project=project,
        input_message_queue=input_message_queue,
    )


def _create_task_thread(
    local_task: Task,
    local_task_state: AgentTaskStateV1,
    environment: LocalEnvironment,
    services: ServiceCollectionForTask,
    project: Project,
    input_message_queue: Queue[Message],
) -> ObservableThread:
    task_data = local_task.input_data
    assert isinstance(task_data, AgentTaskInputsV1)
    return ObservableThread(
        target=_run_agent_in_environment,
        kwargs=dict(
            task=local_task,
            task_data=task_data,
            task_state=local_task_state,
            input_message_queue=input_message_queue,
            environment=environment,
            services=services,
            project=project,
            settings=services.settings,
        ),
        silenced_exceptions=(AgentShutdownCleanly,),
        suppressed_exceptions=(AgentShutdownCleanly,),
        daemon=True,
    )


@pytest.fixture
def running_task_thread(
    task_thread: ObservableThread,
    input_message_queue: Queue[Message],
) -> Generator[ObservableThread, None, None]:
    # start the task
    task_thread.start()
    try:
        yield task_thread
    finally:
        _stop_thread(task_thread, input_message_queue)


def wait_for_message_type(
    message_type: type[Message],
    queue_state: list[Message],
    task_id: TaskID,
    services: ServiceCollectionForTask,
    timeout: float = 5.0,
    count: int = 1,
) -> tuple[list[Message], list[Message]]:
    if os.environ.get("IMBUE_MODAL_INTEGRATION_TEST", "False").lower() in ("true", "1", "t"):
        pass
    else:
        # the timings are quite a bit higher variance on computronium, hopefully this helps alleviate these flakes
        timeout *= 4.0
    wait_until(
        lambda: sum(
            isinstance(msg, message_type) for msg in get_all_messages_for_task(task_id, services)[len(queue_state) :]
        )
        >= count,
        timeout=timeout,
    )
    all_messages = get_all_messages_for_task(task_id, services)
    new_messages = all_messages[len(queue_state) :]
    return all_messages, new_messages


# this is only here to make the below tests slightly more fluent
def send_message(input_message_queue: Queue[Message], message: Message) -> None:
    input_message_queue.put_nowait(message)


T = TypeVar("T", bound=Message)


def validate_new_messages(
    new_messages: list[Message], expected_types: list[type[Message] | tuple[type[T], Callable[[T], bool]]]
) -> None:
    assert len(new_messages) >= len(expected_types)
    next_i = 0
    for message in new_messages:
        if next_i >= len(expected_types):
            return
        expected_type = expected_types[next_i]
        if isinstance(expected_type, tuple):
            current_type, validator = expected_type
            if isinstance(message, current_type):
                if validator(message):
                    next_i += 1
        elif isinstance(message, expected_type):
            next_i += 1
    if next_i != len(expected_types):
        new_messages_str = "\n".join([str(x) for x in new_messages])
        raise Exception(
            f"Did not find all expected message types. Found {next_i} out of {len(expected_types)} in:\n{new_messages_str}"
        )


def _write_check_config(environment: LocalEnvironment, content: str) -> None:
    environment.write_file(str(environment.get_workspace_path() / CHECK_CONFIG_PATH), content)


def test_basic_agent_with_system_checks(
    local_task: Task,
    services: ServiceCollectionForTask,
    input_message_queue: Queue[Message],
    running_task_thread: ObservableThread,
) -> None:
    # get the initial state of the message queue
    state = get_all_messages_for_task(local_task.object_id, services)
    # send the initial chat message
    send_message(input_message_queue, ChatInputUserMessage(text="Hello!"))
    # wait for all the checks to finish
    state, new = wait_for_message_type(CheckFinishedRunnerMessage, state, local_task.object_id, services)
    # verify the resulting new messages
    validate_new_messages(
        new,
        [
            RequestStartedAgentMessage,
            RequestSuccessAgentMessage,
            AgentSnapshotRunnerMessage,
            # system check only
            (ChecksDefinedRunnerMessage, lambda x: only(x.check_by_name.keys()) == SCULPTOR_SYSTEM_CHECK_NAME),
            CheckLaunchedRunnerMessage,
            NewSuggestionRunnerMessage,
            CheckFinishedRunnerMessage,
        ],
    )


def test_basic_agent_with_successful_user_checks(
    local_task: Task,
    services: ServiceCollectionForTask,
    input_message_queue: Queue[Message],
    running_task_thread: ObservableThread,
    environment: LocalEnvironment,
) -> None:
    # create a simple check config with a command that always succeeds
    _write_check_config(environment, """my_command = 'echo hello'""")
    # get the initial state of the message queue
    state = get_all_messages_for_task(local_task.object_id, services)
    # send the initial chat message
    send_message(input_message_queue, ChatInputUserMessage(text="Hello!"))
    # wait for all the checks to finish
    state, new = wait_for_message_type(CheckFinishedRunnerMessage, state, local_task.object_id, services, count=2)
    # verify the resulting new messages
    validate_new_messages(
        new,
        [
            AgentSnapshotRunnerMessage,
            # system check and user check
            (ChecksDefinedRunnerMessage, lambda x: len(x.check_by_name.keys()) == 2),
            CheckLaunchedRunnerMessage,
            CheckFinishedRunnerMessage,
        ],
    )
    # should have no suggestions because everything is defined and passed!
    assert not any(isinstance(msg, NewSuggestionRunnerMessage) for msg in new)


def test_basic_agent_with_checks_for_multiple_messages(
    local_task: Task,
    services: ServiceCollectionForTask,
    input_message_queue: Queue[Message],
    running_task_thread: ObservableThread,
) -> None:
    # get the initial state of the message queue
    state = get_all_messages_for_task(local_task.object_id, services)
    # send the initial chat message
    initial_message = ChatInputUserMessage(text="Hello!")
    send_message(input_message_queue, initial_message)
    # wait for all the checks to finish
    state, new = wait_for_message_type(CheckFinishedRunnerMessage, state, local_task.object_id, services)
    # verify the resulting new messages
    validate_new_messages(
        new,
        [
            RequestStartedAgentMessage,
            RequestSuccessAgentMessage,
            AgentSnapshotRunnerMessage,
            (ChecksDefinedRunnerMessage, lambda x: only(x.check_by_name.keys()) == SCULPTOR_SYSTEM_CHECK_NAME),
            CheckLaunchedRunnerMessage,
            NewSuggestionRunnerMessage,
            CheckFinishedRunnerMessage,
        ],
    )
    # verify that all user message ids and run ids are correct
    _assert_single_message_id(new, initial_message.message_id)
    _assert_single_run_id(new)
    # send another message
    next_message = ChatInputUserMessage(text="Let's chat.")
    send_message(input_message_queue, next_message)
    # wait for all the checks to finish
    state, new = wait_for_message_type(CheckFinishedRunnerMessage, state, local_task.object_id, services)
    # verify the resulting new messages
    validate_new_messages(
        new,
        [
            RequestStartedAgentMessage,
            RequestSuccessAgentMessage,
            AgentSnapshotRunnerMessage,
            (ChecksDefinedRunnerMessage, lambda x: only(x.check_by_name.keys()) == SCULPTOR_SYSTEM_CHECK_NAME),
            CheckLaunchedRunnerMessage,
            NewSuggestionRunnerMessage,
            CheckFinishedRunnerMessage,
        ],
    )
    # verify that all user message ids and run ids are correct
    _assert_single_message_id(new, next_message.message_id)
    _assert_single_run_id(new)


def _assert_single_message_id(new: list[Message], single_message_id: AgentMessageID) -> None:
    user_request_ids = set([x.for_user_message_id for x in new if isinstance(x, (AgentSnapshotRunnerMessage))]).union(
        set(
            [
                x.user_message_id
                for x in new
                if isinstance(x, (ChecksDefinedRunnerMessage, CheckLaunchedRunnerMessage, CheckFinishedRunnerMessage))
            ]
        )
    )
    assert only(user_request_ids) == single_message_id


def _assert_single_run_id(new: list[Message]) -> None:
    run_ids = set(
        [
            x.run_id
            for x in new
            if isinstance(x, (NewSuggestionRunnerMessage, CheckLaunchedRunnerMessage, CheckFinishedRunnerMessage))
        ]
    )
    assert len(run_ids) == 1, f"Expected a single run id, got {run_ids}"


def test_basic_agent_with_failing_user_check(
    local_task: Task,
    services: ServiceCollectionForTask,
    input_message_queue: Queue[Message],
    running_task_thread: ObservableThread,
    environment: LocalEnvironment,
) -> None:
    # create a simple check config with a command that always succeeds
    _write_check_config(environment, """my_command = 'echo oops && exit 1'""")
    # get the initial state of the message queue
    state = get_all_messages_for_task(local_task.object_id, services)
    # send the initial chat message
    send_message(input_message_queue, ChatInputUserMessage(text="Hello!"))
    # wait for all the checks to finish
    state, new = wait_for_message_type(CheckFinishedRunnerMessage, state, local_task.object_id, services, count=2)
    # verify the resulting new messages
    validate_new_messages(
        new,
        [
            AgentSnapshotRunnerMessage,
            # system check and user check
            (ChecksDefinedRunnerMessage, lambda x: len(x.check_by_name.keys()) == 2),
            CheckLaunchedRunnerMessage,
            (NewSuggestionRunnerMessage, lambda x: only(x.suggestions).title == "Fix my_command"),
            CheckFinishedRunnerMessage,
        ],
    )


def test_basic_agent_with_failing_and_passing_user_checks(
    local_task: Task,
    services: ServiceCollectionForTask,
    input_message_queue: Queue[Message],
    running_task_thread: ObservableThread,
    environment: LocalEnvironment,
) -> None:
    # create a simple check config with a command that always succeeds
    _write_check_config(environment, """my_command = 'echo oops && exit 1'\nmy_other_command = 'echo hi'""")
    # get the initial state of the message queue
    state = get_all_messages_for_task(local_task.object_id, services)
    # send the initial chat message
    send_message(input_message_queue, ChatInputUserMessage(text="Hello!"))
    # wait for all the checks to finish
    state, new = wait_for_message_type(CheckFinishedRunnerMessage, state, local_task.object_id, services, count=3)
    # verify the resulting new messages
    validate_new_messages(
        new,
        [
            AgentSnapshotRunnerMessage,
            # system check and user check
            (ChecksDefinedRunnerMessage, lambda x: len(x.check_by_name.keys()) == 3),
            CheckLaunchedRunnerMessage,
            (NewSuggestionRunnerMessage, lambda x: only(x.suggestions).title == "Fix my_command"),
            CheckFinishedRunnerMessage,
        ],
    )


def test_rerunning_user_check(
    local_task: Task,
    services: ServiceCollectionForTask,
    input_message_queue: Queue[Message],
    running_task_thread: ObservableThread,
    environment: LocalEnvironment,
) -> None:
    # create a simple check config with a command that always succeeds
    _write_check_config(environment, """my_command = 'echo hello'""")
    # get the initial state of the message queue
    state = get_all_messages_for_task(local_task.object_id, services)
    # send the initial chat message
    initial_message = ChatInputUserMessage(text="Hello!")
    send_message(input_message_queue, initial_message)
    # wait for all the checks to finish
    state, new = wait_for_message_type(CheckFinishedRunnerMessage, state, local_task.object_id, services, count=2)
    # verify the resulting new messages
    validate_new_messages(
        new,
        [
            AgentSnapshotRunnerMessage,
            (ChecksDefinedRunnerMessage, lambda x: len(x.check_by_name.keys()) == 2),
            CheckLaunchedRunnerMessage,
            CheckFinishedRunnerMessage,
        ],
    )
    _run_id = only(
        set(
            [
                x.run_id
                for x in new
                if (
                    isinstance(x, (CheckFinishedRunnerMessage, CheckLaunchedRunnerMessage))
                    and x.check.name == "my_command"
                )
            ]
        )
    )
    # send a message to re-run the check
    send_message(
        input_message_queue,
        RestartCheckUserMessage(user_message_id=initial_message.message_id, check_name="my_command"),
    )
    # wait for all the checks to finish
    state, new = wait_for_message_type(CheckFinishedRunnerMessage, state, local_task.object_id, services)
    get_all_messages_for_task(local_task.object_id, services)
    # verify the resulting new messages
    validate_new_messages(new, [CheckLaunchedRunnerMessage, CheckFinishedRunnerMessage])
    # assert that there are no suggestions
    assert not any(isinstance(msg, NewSuggestionRunnerMessage) for msg in new)


def test_manual_checks(
    local_task: Task,
    services: ServiceCollectionForTask,
    input_message_queue: Queue[Message],
    running_task_thread: ObservableThread,
    environment: LocalEnvironment,
) -> None:
    # create a simple check config with a command that always succeeds
    _write_check_config(environment, """[my_command]\ncommand = 'echo oops && exit 1'\ntrigger = 'MANUAL'""")
    # get the initial state of the message queue
    state = get_all_messages_for_task(local_task.object_id, services)
    # send the initial chat message
    initial_message = ChatInputUserMessage(text="Hello!")
    send_message(input_message_queue, initial_message)
    # wait for all the checks to finish
    state, new = wait_for_message_type(CheckFinishedRunnerMessage, state, local_task.object_id, services)
    # verify the resulting new messages
    validate_new_messages(
        new,
        [
            AgentSnapshotRunnerMessage,
            # system check and user check
            (ChecksDefinedRunnerMessage, lambda x: len(x.check_by_name.keys()) == 2),
            CheckLaunchedRunnerMessage,
            CheckFinishedRunnerMessage,
        ],
    )
    # should have no suggestions/launched/finished events
    check_messages = list(
        msg
        for msg in new
        if isinstance(msg, (CheckLaunchedRunnerMessage, CheckFinishedRunnerMessage, NewSuggestionRunnerMessage))
    )
    failure_str = "\n".join(str(x) for x in check_messages)
    # we should NOT have run the manual check by default
    assert len(check_messages) == 2, f"Expected only system check messages, got: \n{failure_str}"
    # but if we send a user message to run it, it should be run:
    send_message(
        input_message_queue,
        RestartCheckUserMessage(user_message_id=initial_message.message_id, check_name="my_command"),
    )
    # wait for all the checks to finish
    state, new = wait_for_message_type(CheckFinishedRunnerMessage, state, local_task.object_id, services)
    get_all_messages_for_task(local_task.object_id, services)
    # verify the resulting new messages
    validate_new_messages(new, [CheckLaunchedRunnerMessage, CheckFinishedRunnerMessage])


def test_user_can_stop_check(
    local_task: Task,
    services: ServiceCollectionForTask,
    input_message_queue: Queue[Message],
    running_task_thread: ObservableThread,
    environment: LocalEnvironment,
) -> None:
    # create a simple check config with a command that always succeeds but takes a while
    _write_check_config(environment, """my_command = 'sleep 10 && echo hello'""")
    # get the initial state of the message queue
    state = get_all_messages_for_task(local_task.object_id, services)
    # send the initial chat message
    initial_message = ChatInputUserMessage(text="Hello!")
    send_message(input_message_queue, initial_message)
    # wait for all the checks to finish
    state, new = wait_for_message_type(CheckLaunchedRunnerMessage, state, local_task.object_id, services)
    # verify the resulting new messages
    validate_new_messages(
        new,
        [
            AgentSnapshotRunnerMessage,
            (ChecksDefinedRunnerMessage, lambda x: len(x.check_by_name.keys()) == 2),
            CheckLaunchedRunnerMessage,
        ],
    )
    run_id = only(
        set([x.run_id for x in new if isinstance(x, CheckLaunchedRunnerMessage) and x.check.name == "my_command"])
    )
    # we should NOT see that the check finished:
    assert not any(isinstance(x, CheckFinishedRunnerMessage) and x.check.name == "my_command" for x in new)
    # get the system check out-of-the-way if necessary:
    if not any(isinstance(x, CheckFinishedRunnerMessage) for x in new):
        state, new = wait_for_message_type(CheckFinishedRunnerMessage, state, local_task.object_id, services)
    # send a message to stop the check
    send_message(
        input_message_queue,
        StopCheckUserMessage(user_message_id=initial_message.message_id, run_id=run_id, check_name="my_command"),
    )
    # wait for all the checks to finish
    state, new = wait_for_message_type(CheckFinishedRunnerMessage, state, local_task.object_id, services)
    get_all_messages_for_task(local_task.object_id, services)
    # verify the resulting new messages
    validate_new_messages(
        new,
        [
            (
                CheckFinishedRunnerMessage,
                lambda x: x.check.name == "my_command" and x.finished_reason == CheckFinishedReason.STOPPED,
            )
        ],
    )
    # assert that there are no suggestions
    assert not any(isinstance(msg, NewSuggestionRunnerMessage) for msg in new)


def test_local_check_canceled_on_next_message(
    local_task: Task,
    services: ServiceCollectionForTask,
    input_message_queue: Queue[Message],
    running_task_thread: ObservableThread,
    environment: LocalEnvironment,
) -> None:
    # create a simple check config with a command that always succeeds but takes a while
    _write_check_config(environment, """my_command = 'sleep 10 && echo hello'""")
    # get the initial state of the message queue
    state = get_all_messages_for_task(local_task.object_id, services)
    # send the initial chat message
    initial_message = ChatInputUserMessage(text="Hello!")
    send_message(input_message_queue, initial_message)
    # wait for all the checks to finish
    state, new = wait_for_message_type(CheckLaunchedRunnerMessage, state, local_task.object_id, services)
    # verify the resulting new messages
    validate_new_messages(
        new,
        [
            AgentSnapshotRunnerMessage,
            ChecksDefinedRunnerMessage,
            CheckLaunchedRunnerMessage,
        ],
    )
    # we should NOT see that the check finished:
    assert not any(isinstance(x, CheckFinishedRunnerMessage) and x.check.name == "my_command" for x in new)
    # send another message
    next_message = ChatInputUserMessage(text="Let's chat.")
    send_message(input_message_queue, next_message)
    # the check should be stopped then relaunched
    state, new = wait_for_message_type(CheckLaunchedRunnerMessage, state, local_task.object_id, services)
    # verify the resulting new messages
    validate_new_messages(
        new,
        [
            (
                CheckFinishedRunnerMessage,
                lambda x: x.check.name == "my_command" and x.finished_reason == CheckFinishedReason.INTERRUPTED,
            ),
            RequestStartedAgentMessage,
            (CheckLaunchedRunnerMessage, lambda x: x.check.name == "my_command"),
        ],
    )


def test_agent_suggestion_restore(
    local_task: Task,
    services: ServiceCollectionForTask,
    input_message_queue: Queue[Message],
    # note that the thread is NOT running in this case!!
    task_thread: ObservableThread,
    environment: LocalEnvironment,
    project: Project,
) -> None:
    # start the thread
    task_thread.start()
    try:
        # add a command that will generate some suggestions
        _write_check_config(environment, """my_command = 'echo oops && exit 1'""")
        # get the initial state of the message queue
        state = get_all_messages_for_task(local_task.object_id, services)
        # send the initial chat message
        send_message(input_message_queue, ChatInputUserMessage(text="Hello!"))
        # wait for all the checks to finish
        state, new = wait_for_message_type(CheckFinishedRunnerMessage, state, local_task.object_id, services, count=2)
        # verify the resulting new messages
        validate_new_messages(
            new,
            [
                (ChecksDefinedRunnerMessage, lambda x: len(x.check_by_name.keys()) == 2),
                CheckLaunchedRunnerMessage,
                NewSuggestionRunnerMessage,
                CheckFinishedRunnerMessage,
            ],
        )
        # stop the thread
        input_message_queue.put_nowait(StopAgentUserMessage())
        task_thread.join(timeout=_THREAD_TIMEOUT)
        assert not task_thread.is_alive(), "Agent thread did not shut down properly for fixture"
        # now let's run the thread again and see if everything is restored! :)
        current_task_state = _load_current_task_state(project, services)
        next_input_message_queue = Queue[Message]()
        next_run_thread = _create_task_thread(
            local_task=local_task,
            local_task_state=current_task_state,
            environment=environment,
            services=services,
            project=project,
            input_message_queue=next_input_message_queue,
        )
        next_run_thread.start()
        try:
            state, new = wait_for_message_type(NewSuggestionRunnerMessage, state, local_task.object_id, services)
            validate_new_messages(
                new,
                [
                    ChecksDefinedRunnerMessage,
                    CheckFinishedRunnerMessage,
                    CheckFinishedRunnerMessage,
                    NewSuggestionRunnerMessage,
                ],
            )
        finally:
            _stop_thread(next_run_thread, next_input_message_queue)

    # stop the thread
    finally:
        _stop_thread(task_thread, input_message_queue)


def _load_current_task_state(project: Project, services: ServiceCollectionForTask) -> AgentTaskStateV1:
    with services.data_model_service.open_task_transaction() as transaction:
        existing_tasks = transaction.get_tasks_for_project(
            outcomes={TaskState.QUEUED}, project_id=project.object_id, is_archived=False, max_results=8
        )
        existing_task = only(existing_tasks)
        current_task_state = existing_task.current_state
        assert isinstance(current_task_state, AgentTaskStateV1)
    return current_task_state


# FIXME(18d4c9a0-35b8-4a31-9f60-b6bb891428a8): switch away from this when we have a better way of making a task shutdown
def _stop_thread(task_thread: ObservableThread, input_message_queue: Queue[Message]) -> None:
    if task_thread.is_alive():
        input_message_queue.put_nowait(StopAgentUserMessage())
        task_thread.join(timeout=_THREAD_TIMEOUT)
        assert not task_thread.is_alive(), "Agent thread did not shut down properly for fixture"


# TODO: add a test for resuming when previous checks and suggestions no longer load
