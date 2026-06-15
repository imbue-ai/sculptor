from queue import Queue

from sculptor.agents.hello_agent.agent_wrapper import HelloAgent
from sculptor.interfaces.agents.agent import RequestSuccessAgentMessage
from sculptor.interfaces.agents.agent import StopAgentUserMessage


class _HelloForTest(HelloAgent):
    """``wait`` is stubbed to a no-op so the ``StopAgentUserMessage`` path can be
    exercised without the message-processing thread / environment wiring that
    ``model_construct`` leaves unset."""

    def wait(self, timeout: float) -> int | None:
        return 0


def _drain(queue: Queue) -> list:
    items = []
    while not queue.empty():
        items.append(queue.get())
    return items


def test_stop_message_does_not_emit_request_success() -> None:
    """HelloAgent overrides ``push_message`` with its own stop handler; like the
    base agent, a stopped turn must NOT emit a ``RequestSuccessAgentMessage``.

    Regression test: the stop handler bracketed the stop in ``_handle_user_message``
    but never set ``self._is_stopping = True``, so the inherited clean-exit guard
    was dead and an interrupted turn reported success.
    """
    wrapper = _HelloForTest.model_construct()

    wrapper.push_message(StopAgentUserMessage())

    emitted = _drain(wrapper._output_messages)
    succeeded = [m for m in emitted if isinstance(m, RequestSuccessAgentMessage)]
    assert succeeded == [], f"a stopped turn must not emit RequestSuccess; got {emitted}"
