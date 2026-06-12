"""The Hello-agent harness — trivial non-Claude implementor of `Harness`.

`HelloAgent` is an echo test stub. Agent construction is owned by the
registry, so this module does not import `HelloAgent`.

`HelloHarness` is bare: it supplies the minimum region (`name`) and
inherits the trivial-answer defaults for every
capability-region member. Identity-surface members no longer live on the
base, so there is nothing for the stub to "supply as empty" — the absence
of any Claude-style identity is the natural shape of a non-Claude harness.
"""

from __future__ import annotations

from sculptor.interfaces.agents.harness import Harness


class HelloHarness(Harness):
    name: str = "hello"


HELLO_HARNESS: HelloHarness = HelloHarness()
