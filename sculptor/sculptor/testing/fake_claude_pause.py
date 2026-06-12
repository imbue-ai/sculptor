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
