# `Agent` interface versions

The point of an `Agent` is to "complete" a `Task`.

`Agent`s have the following properties:
- They are guaranteed to have an initial message, which serves as the goal of that `Task`.
- They will be run in the specified `Environment`.
- They emit a sequence of `AgentMessage`s to communicate their progress and results.
- They should react to `AgentMessage`s sent to them by the user or controlling process.
- They can be interrupted (like any normal task). Because of this, they should support resuming from a previous state.
- They can be restricted and limited in various ways, such as by time, resources, network access, information (eg, secret) availability, etc.
- They have a notion of whether they are blocked or not (ie, if they are waiting for user input.)
- They have a notion of whether they are complete or not (ie, if they have finished their task.)
- They may ask questions, make suggestions, or provide other information to the user.
- They must produce at least one output (eg, a branch, a file, a piece of text, etc.) when they are complete.

Programmatically, the core `Agent` interface is very simple --
`Agent`s are tasked with performing a specific goal within an `Environment`,
and they output both the raw text output buffer (`output_text`) and a sequence of `AgentMessage`s.
Users may send `AgentMessage`s to the agent while it is running as well.

When the agent is done, the `is_complete` property will be `True`,
and there will be at least one artifact in the `artifacts` property.

The most recent version of the `Agent` interface is `v1`.

See the [`./v1/agent.py`](./v1/agent.py) for the exact definition of the interface.
