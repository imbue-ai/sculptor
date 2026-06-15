"""The terminal harness — the `Harness` for terminal agents.

Terminal agents have no chat surface at all: their main panel is a PTY
terminal and Sculptor never parses their output. There is no message
stream, so every capability — including `supports_chat_interface`, the
coarse main-panel switch — is uniformly false.

Agent construction never happens for terminal configs: they are dispatched
to the dedicated terminal task handler, not `create_agent_for_run`.
"""

from __future__ import annotations

from sculptor.interfaces.agents.harness import Harness
from sculptor.interfaces.agents.harness import HarnessCapabilities


class TerminalHarness(Harness):
    name: str = "terminal"

    def capabilities(self) -> HarnessCapabilities:
        # Uniformly false: terminal agents have no message stream, so no
        # chat-derived affordance can apply (see module docstring).
        return HarnessCapabilities(
            supports_chat_interface=False,
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
        )


TERMINAL_HARNESS: TerminalHarness = TerminalHarness()
