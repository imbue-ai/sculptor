"""Pause a fake_claude agent until the test releases it.

Use this in place of ``fake_claude:sleep`` whenever a test needs the agent to
stay busy across an unbounded sequence of UI actions: there is no wall-clock,
so CI overhead can't race the busy window.
"""

import tempfile
import uuid
from pathlib import Path


class FakeClaudePause:
    """A signaled pause for fake_claude.

    Pass ``prompt`` to the agent to start a paused turn. Call ``release()``
    when the test is ready for the agent to finish its turn naturally.

    For commands other than the top-level ``wait_for_file`` (e.g. a pause
    embedded inside ``background_subagent``), embed ``release_path`` into the
    command's args and the same ``release()`` will unblock it.
    """

    def __init__(self) -> None:
        self.release_path = Path(tempfile.gettempdir()) / f"fake_claude_pause_{uuid.uuid4().hex}"
        self.prompt = f'fake_claude:wait_for_file `{{"path": "{self.release_path}"}}`'

    def release(self) -> None:
        """Let fake_claude's current turn finish naturally."""
        self.release_path.touch()


class FakeClaudeTrigger:
    """A signaled completion trigger for a fake_claude background task.

    Pass ``trigger_path`` to a ``start_background_task`` command to arm a
    background task whose completion the test controls. Call ``fire()`` when
    the test wants the task to complete: fake_claude then emits the task's
    ``task_updated`` + ``task_notification`` and runs its scripted reaction
    cycle. The same path can be handed to a ``complete_background_task`` step so
    a borrowed turn completes the task inline mid-cycle instead.

    Mirrors ``FakeClaudePause``: a unique sentinel file plus a method that
    creates it, so completion timing is signaled rather than raced against a
    wall-clock.
    """

    def __init__(self) -> None:
        self.trigger_path = Path(tempfile.gettempdir()) / f"fake_claude_trigger_{uuid.uuid4().hex}"

    def fire(self) -> None:
        """Complete the armed background task now."""
        self.trigger_path.touch()
