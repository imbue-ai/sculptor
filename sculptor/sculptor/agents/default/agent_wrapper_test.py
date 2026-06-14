from queue import Queue

from sculptor.agents.default.agent_wrapper import DefaultAgentWrapper
from sculptor.interfaces.agents.agent import RequestStartedAgentMessage
from sculptor.interfaces.agents.agent import RequestSuccessAgentMessage
from sculptor.interfaces.agents.agent import ResumeAgentResponseRunnerMessage
from sculptor.primitives.ids import AgentMessageID
from sculptor.state.messages import LLMModel


class _WrapperForTest(DefaultAgentWrapper):
    """Concrete DefaultAgentWrapper for unit tests.

    ``DefaultAgentWrapper`` only leaves ``wait`` abstract; stubbing it makes the
    class instantiable so ``model_construct`` can build one without the heavy
    environment / harness wiring that the bracketed ``_handle_user_message`` path
    does not touch.
    """

    def wait(self, timeout: float) -> int:
        return 0


def _drain(queue: Queue) -> list:
    items = []
    while not queue.empty():
        items.append(queue.get())
    return items


def test_resume_turn_uses_for_user_message_id_as_request_id() -> None:
    """A ``ResumeAgentResponseRunnerMessage`` continues an earlier user turn, so the
    per-turn ``RequestStarted`` / ``RequestSuccess`` it brackets must carry that
    turn's id (``for_user_message_id``) -- NOT the resume message's own freshly
    generated ``message_id``.

    When they carry the resume's own id instead, the resumed turn's completion
    never matches the original chat message: the run-loop's
    ``is_agent_turn_finished`` (``v1.py``, matches the tracked
    ``ChatInputUserMessage`` id) never fires, so a queued follow-up message is
    never dequeued, and the frontend projection's ``current_request_id`` never
    clears, so the StatusPill stays stuck on "Streaming"/"Thinking" after a
    restart.
    """
    original_user_message_id = AgentMessageID()
    resume_message = ResumeAgentResponseRunnerMessage(
        for_user_message_id=original_user_message_id,
        model_name=LLMModel.CLAUDE_4_SONNET,
    )
    # Sanity: the resume message has its own id, distinct from the turn it resumes.
    assert resume_message.message_id != original_user_message_id

    # model_construct() builds a typed DefaultAgentWrapper without the heavy
    # environment / harness wiring: ``_handle_user_message``'s start + clean-exit
    # path only touches the ``_output_messages`` / ``_is_stopping`` /
    # ``_was_interrupted`` private attrs, which get their PrivateAttr defaults.
    wrapper = _WrapperForTest.model_construct()

    # Enter the per-turn bracket (emits RequestStarted) and exit cleanly
    # (emits RequestSuccess), as a finished turn would.
    with wrapper._handle_user_message(resume_message):
        pass

    emitted = _drain(wrapper._output_messages)
    started = [m for m in emitted if isinstance(m, RequestStartedAgentMessage)]
    succeeded = [m for m in emitted if isinstance(m, RequestSuccessAgentMessage)]
    assert len(started) == 1, f"expected exactly one RequestStarted, got {emitted}"
    assert len(succeeded) == 1, f"expected exactly one RequestSuccess, got {emitted}"
    assert started[0].request_id == original_user_message_id, (
        f"RequestStarted must use for_user_message_id; got {started[0].request_id}"
    )
    assert succeeded[0].request_id == original_user_message_id, (
        f"RequestSuccess must use for_user_message_id; got {succeeded[0].request_id}"
    )
