"""Regression tests for CodingAgentTaskView.status after restart mid-agent-turn.

Historical context: this file originally enforced "status RUNNING after restart
when the only completion is a RequestStopped, because the agent is re-processing."
That behavior was a workaround for a prompt-replay bug: when Sculptor was SIGTERM'd
mid-turn the runner used to silently re-deliver the prompt to Claude on the next
agent run, so RequestStopped really did precede a re-processing window.

With those bugs fixed at the runner layer, the re-processing no longer happens.
RequestStopped now genuinely means "this chat is settled; the user can send a new
message." Status should be READY, not RUNNING. The exclusion of RequestStopped
from ``request_finished_messages`` in ``derived.py`` has been removed accordingly,
and the test below has been updated to assert the new behavior.
"""

from sculptor.config.settings import SculptorSettings
from sculptor.database.models import AgentTaskInputsV2
from sculptor.database.models import AgentTaskStateV2
from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.foundation.serialization import SerializedException
from sculptor.interfaces.agents.agent import AskUserQuestionAgentMessage
from sculptor.interfaces.agents.agent import ClaudeCodeSDKAgentConfig
from sculptor.interfaces.agents.agent import EnvironmentAcquiredRunnerMessage
from sculptor.interfaces.agents.agent import HelloAgentConfig
from sculptor.interfaces.agents.agent import RequestFailureAgentMessage
from sculptor.interfaces.agents.agent import RequestStoppedAgentMessage
from sculptor.interfaces.agents.agent import RequestSuccessAgentMessage
from sculptor.interfaces.agents.agent import TerminalAgentConfig
from sculptor.interfaces.agents.agent import TerminalAgentSignalRunnerMessage
from sculptor.interfaces.agents.agent import TerminalStatusSignal
from sculptor.interfaces.agents.harness import HarnessCapabilities
from sculptor.interfaces.agents.tasks import TaskState
from sculptor.primitives.ids import AgentMessageID
from sculptor.primitives.ids import AssistantMessageID
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import ToolUseID
from sculptor.primitives.ids import UserReference
from sculptor.primitives.ids import WorkspaceID
from sculptor.state.chat_state import AskUserQuestionData
from sculptor.state.chat_state import QuestionOption
from sculptor.state.chat_state import ToolUseBlock
from sculptor.state.chat_state import UserQuestion
from sculptor.state.messages import ChatInputUserMessage
from sculptor.state.messages import ResponseBlockAgentMessage
from sculptor.web.derived import CodingAgentTaskView
from sculptor.web.derived import TaskStatus
from sculptor.web.derived import create_initial_task_view


def _make_task(*, outcome: TaskState = TaskState.RUNNING) -> Task:
    workspace_id = WorkspaceID()
    return Task(
        object_id=TaskID(),
        user_reference=UserReference("test-user"),
        organization_reference=OrganizationReference("test-org"),
        project_id=ProjectID(),
        input_data=AgentTaskInputsV2(
            agent_config=ClaudeCodeSDKAgentConfig(),
            git_hash="abc123",
            system_prompt=None,
        ),
        current_state=AgentTaskStateV2(workspace_id=workspace_id),
        outcome=outcome,
    )


def _make_task_view(task: Task) -> CodingAgentTaskView:
    settings = SculptorSettings()
    view = create_initial_task_view(task, settings)
    assert isinstance(view, CodingAgentTaskView)
    view.update_task(task)
    return view


def _make_serialized_exception() -> SerializedException:
    return SerializedException.model_construct(
        exception="ProcessExitedError",
        args=("Process exited with signal SIGTERM",),
        traceback_dict={},
    )


def test_status_is_ready_after_request_stopped_and_environment_reacquired() -> None:
    """Post-restart message sequence with a SIGTERM'd previous turn settles into READY.

    Message sequence after a restart where the user's prompt was SIGTERM'd:
    1. ChatInputUserMessage — the original user request (persisted)
    2. RequestStoppedAgentMessage — emitted on SIGTERM (persisted)
    3. EnvironmentAcquiredRunnerMessage — new agent acquires environment (ephemeral)

    With the agent-runner fixes landed (hypothesis #1 / #4), the interrupted
    prompt is recorded as processed and NOT re-delivered to Claude on the next
    agent run. The post-restart agent is therefore idle — the user can send a
    new message — so status should be READY.

    This test previously asserted RUNNING as a workaround for the replay bug
    (RequestStopped was excluded from "finished" so status stayed RUNNING during
    the unwanted re-processing). That exclusion is gone now that the runner
    doesn't re-process.
    """
    task = _make_task()
    view = _make_task_view(task)

    user_message_id = AgentMessageID()

    view.add_message(ChatInputUserMessage(message_id=user_message_id, text="Do something"))
    view.add_message(
        RequestStoppedAgentMessage.model_construct(
            request_id=user_message_id,
            error=_make_serialized_exception(),
        )
    )
    view.add_message(
        EnvironmentAcquiredRunnerMessage.model_construct(
            message_id=AgentMessageID(),
            environment=None,
        )
    )

    assert view.status == TaskStatus.READY


def test_status_is_ready_when_request_succeeded() -> None:
    """Status should be READY when all requests have a success completion message.

    This is the normal case: the agent completed the request successfully.
    """
    task = _make_task()
    view = _make_task_view(task)

    user_message_id = AgentMessageID()

    view.add_message(ChatInputUserMessage(message_id=user_message_id, text="Do something"))
    view.add_message(
        EnvironmentAcquiredRunnerMessage.model_construct(
            message_id=AgentMessageID(),
            environment=None,
        )
    )
    view.add_message(RequestSuccessAgentMessage.model_construct(request_id=user_message_id))

    assert view.status == TaskStatus.READY


def test_status_is_building_without_environment_acquired() -> None:
    """Status should be BUILDING when the environment hasn't been acquired yet."""
    task = _make_task()
    view = _make_task_view(task)

    view.add_message(ChatInputUserMessage(message_id=AgentMessageID(), text="Do something"))

    assert view.status == TaskStatus.BUILDING


def test_status_is_waiting_when_auq_pending_during_in_flight_request() -> None:
    """Status should be WAITING when an AUQ has been emitted but the request is still in flight.

    Under the in-process MCP delivery flow, the agent's ``tools/call`` is held
    while waiting for the user's answer — the request stays alive (no
    ``PersistentRequestComplete``). The previous ``status`` derivation gated
    the WAITING-vs-RUNNING decision behind the request being formally
    complete, so AUQ-pending tasks were misreported as RUNNING and the
    workspace peek's "needs your input" banner never surfaced.

    Regression for the workspace_peek integration tests
    ``test_workspace_peek_popover_waiting_state`` and
    ``test_workspace_peek_waiting_overrides_running_in_status_dot``.
    """
    task = _make_task()
    view = _make_task_view(task)

    user_message_id = AgentMessageID()
    view.add_message(ChatInputUserMessage(message_id=user_message_id, text="Pick a color"))
    view.add_message(
        EnvironmentAcquiredRunnerMessage.model_construct(
            message_id=AgentMessageID(),
            environment=None,
        )
    )
    view.add_message(
        AskUserQuestionAgentMessage(
            message_id=AgentMessageID(),
            question_data=AskUserQuestionData(
                questions=[
                    UserQuestion(
                        question="Which color?",
                        header="Color",
                        options=[
                            QuestionOption(label="Red", description=""),
                            QuestionOption(label="Blue", description=""),
                        ],
                        multi_select=False,
                    )
                ],
                tool_use_id="toolu_test",
            ),
        )
    )
    # Note: NO RequestSuccess / RequestComplete — the MCP call is held mid-turn.

    assert view.status == TaskStatus.WAITING


def test_status_is_not_waiting_for_malformed_ask_user_question_tool_use_block() -> None:
    """A persisted ``mcp__sculptor__ask_user_question`` ToolUseBlock with input
    that fails strict validation must NOT pin the task into WAITING.

    The MCP server rejected such a call with a JSON-RPC error so the agent has
    moved on; surfacing WAITING here would leave the workspace stuck in the
    yellow ``Waiting for input`` state in the workspace peek popover.
    """
    task = _make_task()
    view = _make_task_view(task)

    user_message_id = AgentMessageID()
    view.add_message(ChatInputUserMessage(message_id=user_message_id, text="Pick a color"))
    view.add_message(
        EnvironmentAcquiredRunnerMessage.model_construct(
            message_id=AgentMessageID(),
            environment=None,
        )
    )
    # Malformed: ``multiSelect: 'false'`` is a string, not a bool. Strict
    # validation rejects this — the MCP server already responded with an error.
    malformed_block = ToolUseBlock(
        id=ToolUseID("toolu_malformed"),
        name="mcp__sculptor__ask_user_question",
        input={
            "questions": [
                {
                    "question": "Pick one",
                    "header": "Color",
                    "options": [{"label": "Red", "description": ""}],
                    "multiSelect": "false",
                }
            ]
        },
    )
    view.add_message(
        ResponseBlockAgentMessage.model_construct(
            role="assistant",
            assistant_message_id=AssistantMessageID("am_test"),
            message_id=AgentMessageID(),
            content=(malformed_block,),
        )
    )
    view.add_message(RequestSuccessAgentMessage.model_construct(request_id=user_message_id))

    assert view.status != TaskStatus.WAITING


def test_status_is_waiting_for_exit_plan_mode_tool_use_block() -> None:
    """``mcp__sculptor__exit_plan_mode`` advertises an empty input schema —
    any tool_use of it (legacy built-in name or MCP FQN, any input) pins the
    task into WAITING until the user approves/dismisses.
    """
    task = _make_task()
    view = _make_task_view(task)

    user_message_id = AgentMessageID()
    view.add_message(ChatInputUserMessage(message_id=user_message_id, text="Plan something"))
    view.add_message(
        EnvironmentAcquiredRunnerMessage.model_construct(
            message_id=AgentMessageID(),
            environment=None,
        )
    )
    plan_block = ToolUseBlock(
        id=ToolUseID("toolu_plan"),
        name="mcp__sculptor__exit_plan_mode",
        input={},
    )
    view.add_message(
        ResponseBlockAgentMessage.model_construct(
            role="assistant",
            assistant_message_id=AssistantMessageID("am_plan"),
            message_id=AgentMessageID(),
            content=(plan_block,),
        )
    )

    assert view.status == TaskStatus.WAITING


def test_status_is_not_waiting_when_auq_request_failed_without_an_answer() -> None:
    """SCU-530 follow-on: after the in-flight request that emitted an AUQ fails,
    the task must not stay pinned in ``WAITING``.

    Symptom: the workspace tab and agent dot stay yellow ("Waiting for your
    input") even though the agent's request has died and the runner has
    already cleared its internal ``is_waiting_for_question_answer`` flag (the
    earlier half of the SCU-530 fix). The derived status walked messages in
    reverse looking for an unanswered AUQ tool block and never noticed that
    its surrounding request had since failed — so the historical AUQ from
    the dead turn kept the task yellow forever.

    Sequence: ChatInputUserMessage → EnvironmentAcquired →
    ResponseBlock(AUQ ToolUse) → AskUserQuestionAgentMessage →
    RequestFailureAgentMessage(same request_id).
    """
    task = _make_task()
    view = _make_task_view(task)

    user_message_id = AgentMessageID()
    view.add_message(ChatInputUserMessage(message_id=user_message_id, text="Pick a color"))
    view.add_message(
        EnvironmentAcquiredRunnerMessage.model_construct(
            message_id=AgentMessageID(),
            environment=None,
        )
    )
    auq_block = ToolUseBlock(
        id=ToolUseID("toolu_auq"),
        name="mcp__sculptor__ask_user_question",
        input={
            "questions": [
                {
                    "question": "Pick a color",
                    "header": "Color",
                    "options": [
                        {"label": "Red", "description": "warm"},
                        {"label": "Blue", "description": "cool"},
                    ],
                    "multiSelect": False,
                }
            ]
        },
    )
    view.add_message(
        ResponseBlockAgentMessage.model_construct(
            role="assistant",
            assistant_message_id=AssistantMessageID("am_auq"),
            message_id=AgentMessageID(),
            content=(auq_block,),
        )
    )
    view.add_message(
        AskUserQuestionAgentMessage(
            message_id=AgentMessageID(),
            question_data=AskUserQuestionData(
                questions=[
                    UserQuestion(
                        question="Pick a color",
                        header="Color",
                        options=[
                            QuestionOption(label="Red", description="warm"),
                            QuestionOption(label="Blue", description="cool"),
                        ],
                        multi_select=False,
                    )
                ],
                tool_use_id="toolu_auq",
            ),
        )
    )
    view.add_message(
        RequestFailureAgentMessage.model_construct(
            request_id=user_message_id,
            error=_make_serialized_exception(),
        )
    )

    assert view.status != TaskStatus.WAITING


def test_status_is_not_waiting_when_auq_request_was_stopped_without_an_answer() -> None:
    """SCU-530 follow-on, SIGTERM variant: same fix must apply when the AUQ
    request is stopped (e.g. agent received SIGTERM mid-question) rather than
    failed with a Python error. ``RequestStoppedAgentMessage`` and
    ``RequestFailureAgentMessage`` are both ``PersistentRequestCompleteAgentMessage``
    subclasses, so the derived-status fix breaks the reverse walk for either.
    """
    task = _make_task()
    view = _make_task_view(task)

    user_message_id = AgentMessageID()
    view.add_message(ChatInputUserMessage(message_id=user_message_id, text="Pick a color"))
    view.add_message(
        EnvironmentAcquiredRunnerMessage.model_construct(
            message_id=AgentMessageID(),
            environment=None,
        )
    )
    auq_block = ToolUseBlock(
        id=ToolUseID("toolu_auq_stopped"),
        name="mcp__sculptor__ask_user_question",
        input={
            "questions": [
                {
                    "question": "Pick a color",
                    "header": "Color",
                    "options": [
                        {"label": "Red", "description": "warm"},
                        {"label": "Blue", "description": "cool"},
                    ],
                    "multiSelect": False,
                }
            ]
        },
    )
    view.add_message(
        ResponseBlockAgentMessage.model_construct(
            role="assistant",
            assistant_message_id=AssistantMessageID("am_auq_stopped"),
            message_id=AgentMessageID(),
            content=(auq_block,),
        )
    )
    view.add_message(
        AskUserQuestionAgentMessage(
            message_id=AgentMessageID(),
            question_data=AskUserQuestionData(
                questions=[
                    UserQuestion(
                        question="Pick a color",
                        header="Color",
                        options=[
                            QuestionOption(label="Red", description="warm"),
                            QuestionOption(label="Blue", description="cool"),
                        ],
                        multi_select=False,
                    )
                ],
                tool_use_id="toolu_auq_stopped",
            ),
        )
    )
    view.add_message(
        RequestStoppedAgentMessage.model_construct(
            request_id=user_message_id,
            error=_make_serialized_exception(),
        )
    )

    assert view.status != TaskStatus.WAITING


def _make_hello_task() -> Task:
    workspace_id = WorkspaceID()
    return Task(
        object_id=TaskID(),
        user_reference=UserReference("test-user"),
        organization_reference=OrganizationReference("test-org"),
        project_id=ProjectID(),
        input_data=AgentTaskInputsV2(
            agent_config=HelloAgentConfig(),
            git_hash="abc123",
            system_prompt=None,
        ),
        current_state=AgentTaskStateV2(workspace_id=workspace_id),
        outcome=TaskState.RUNNING,
    )


def test_harness_capabilities_for_claude_task_advertises_all_true() -> None:
    view = _make_task_view(_make_task())
    assert view.harness_capabilities == HarnessCapabilities(
        supports_chat_interface=True,
        supports_interactive_backchannel=True,
        supports_skills=True,
        supports_sub_agents=True,
        supports_image_input=True,
        supports_fast_mode=True,
        supports_context_reset=True,
        supports_compaction=True,
        supports_background_tasks=True,
        supports_session_resume=True,
        supports_tool_use_rendering=True,
        supports_file_attachments=True,
        supports_interruption=True,
        supports_file_references=True,
        supports_model_selection=True,
    )


def _make_terminal_task(*, outcome: TaskState = TaskState.RUNNING) -> Task:
    return Task(
        object_id=TaskID(),
        user_reference=UserReference("test-user"),
        organization_reference=OrganizationReference("test-org"),
        project_id=ProjectID(),
        input_data=AgentTaskInputsV2(
            agent_config=TerminalAgentConfig(),
            git_hash="abc123",
            system_prompt=None,
        ),
        current_state=AgentTaskStateV2(workspace_id=WorkspaceID()),
        outcome=outcome,
    )


def test_terminal_task_status_is_building_before_environment() -> None:
    # Unlike chat tasks, a prompt-less terminal task with no environment is
    # still building — the "no user message → READY" special case must not apply.
    view = _make_task_view(_make_terminal_task())
    assert view.status == TaskStatus.BUILDING


def test_terminal_task_status_is_ready_after_environment() -> None:
    view = _make_task_view(_make_terminal_task())
    view.add_message(
        EnvironmentAcquiredRunnerMessage.model_construct(
            message_id=AgentMessageID(),
            environment=None,
        )
    )
    assert view.status == TaskStatus.READY


def test_terminal_task_status_outcome_short_circuits_unchanged() -> None:
    assert _make_task_view(_make_terminal_task(outcome=TaskState.QUEUED)).status == TaskStatus.BUILDING
    assert _make_task_view(_make_terminal_task(outcome=TaskState.FAILED)).status == TaskStatus.ERROR
    assert _make_task_view(_make_terminal_task(outcome=TaskState.DELETED)).status == TaskStatus.READY


def test_harness_capabilities_for_hello_task_are_all_false() -> None:
    view = _make_task_view(_make_hello_task())
    # Hello is a chat agent (its main panel is the chat interface); every
    # per-affordance capability is false.
    assert view.harness_capabilities == HarnessCapabilities(
        supports_chat_interface=True,
        supports_interactive_backchannel=False,
        supports_skills=False,
        supports_sub_agents=False,
        supports_image_input=False,
        supports_fast_mode=False,
        supports_context_reset=False,
        supports_compaction=False,
        supports_background_tasks=False,
        supports_session_resume=False,
        supports_tool_use_rendering=False,
        supports_file_attachments=False,
        supports_interruption=False,
        supports_file_references=False,
        supports_model_selection=False,
    )


def _env_acquired() -> EnvironmentAcquiredRunnerMessage:
    return EnvironmentAcquiredRunnerMessage.model_construct(
        message_id=AgentMessageID(),
        environment=None,
    )


def _signal(signal: TerminalStatusSignal) -> TerminalAgentSignalRunnerMessage:
    return TerminalAgentSignalRunnerMessage(signal=signal)


def test_terminal_status_follows_latest_signal_since_run_start() -> None:
    view = _make_task_view(_make_terminal_task())
    view.add_message(_env_acquired())

    view.add_message(_signal(TerminalStatusSignal.BUSY))
    assert view.status == TaskStatus.RUNNING

    view.add_message(_signal(TerminalStatusSignal.WAITING))
    assert view.status == TaskStatus.WAITING

    # Latest wins.
    view.add_message(_signal(TerminalStatusSignal.BUSY))
    assert view.status == TaskStatus.RUNNING

    view.add_message(_signal(TerminalStatusSignal.IDLE))
    assert view.status == TaskStatus.READY


def test_terminal_status_resets_at_each_run_start() -> None:
    # A pre-re-run WAITING must NOT survive the next run's anchor
    # (stale-status risk).
    view = _make_task_view(_make_terminal_task())
    view.add_message(_env_acquired())
    view.add_message(_signal(TerminalStatusSignal.WAITING))
    assert view.status == TaskStatus.WAITING

    view.add_message(_env_acquired())
    assert view.status == TaskStatus.READY

    view.add_message(_signal(TerminalStatusSignal.BUSY))
    assert view.status == TaskStatus.RUNNING


def test_terminal_status_neutral_after_restart_until_signals_re_drive() -> None:
    # Signals are ephemeral: after a backend restart a fresh view only sees
    # persistent messages, so status is BUILDING pre-anchor and neutral READY
    # once the new run acquires its environment.
    view = _make_task_view(_make_terminal_task())
    assert view.status == TaskStatus.BUILDING
    view.add_message(_env_acquired())
    assert view.status == TaskStatus.READY


def test_terminal_status_outcome_short_circuit_beats_signals() -> None:
    view = _make_task_view(_make_terminal_task(outcome=TaskState.FAILED))
    view.add_message(_env_acquired())
    view.add_message(_signal(TerminalStatusSignal.BUSY))
    assert view.status == TaskStatus.ERROR
