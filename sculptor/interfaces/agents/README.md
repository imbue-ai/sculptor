# `Agent` interface versions

The core `Agent` interface is very simple --
`Agent`s are tasked with performing a specific goal (`orginal_goal`) within an `Environment`,
and they output both the raw text output buffer (`output_text`) and a sequence of `messages`.
Users may send messages to the agent while it is running as well.

When the agent is done, the `is_complete` property will be `True`,
and there will be at least one artifact in the `artifacts` property.

The most recent version of the `Agent` interface is `v1`.

See the [`./v1/agent.py`](./v1/agent.py) for the exact definition of the interface.
