"""The Hello-agent harness — trivial non-Claude implementor of `Harness`.

`HelloAgent` is an echo test stub. Agent construction is owned by the
registry, so this module does not import `HelloAgent`.

`HelloHarness` is near-bare: it supplies the minimum region (`name`) and
inherits the trivial-answer defaults for every capability-region member
except `supports_chat_interface` — hello is a chat agent (its main panel
is the chat interface), so it overrides `capabilities()` to declare that
single truth. Identity-surface members no longer live on the base, so
there is nothing for the stub to "supply as empty" — the absence of any
Claude-style identity is the natural shape of a non-Claude harness.
"""

from __future__ import annotations

from sculptor.interfaces.agents.harness import Harness
from sculptor.interfaces.agents.harness import HarnessCapabilities


class HelloHarness(Harness):
    name: str = "hello"

    def capabilities(self) -> HarnessCapabilities:
        return HarnessCapabilities(
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
        )


HELLO_HARNESS: HelloHarness = HelloHarness()
