# `Agent` interface versions

Conceptually, the purpose of an `Agent` is to perform a specific task or accomplish some goal.

Fundamentally, an `Agent` is extremely simple:
any program that can process a `Message`s (and emit `Message`s) can be considered an `Agent`.

That said, there are a number of additional conventions defined below that make it easier to work with `Agent`s in the `sculptor` ecosystem:

- `Agent`s are guaranteed to have an initial message, which serves as the initial goal.
- `Agent`s will be run in the `Environment` specified in the inputs (`AgentTaskInputsV1`.)
- `Agent`s should emit a sequence of `Message`s to communicate their progress and results.
- `Agent`s should react to `Message`s sent to them by the user or controlling process.
- `Agent`s can be interrupted (like any normal task). Because of this, they should support resuming from a previous state.
- `Agent`s should yield `PersistentRequestCompleteAgentMessage` messages when they have finished processing a message.
  This enables the controlling process to snapshot the state (when there are no pending messages.)
- `Agent`s can be restricted and limited in various ways, such as by time, resources, network access, information (eg, secret) availability, etc.
- `Agent`s should have a notion of whether they are blocked or not (ie, if they are waiting for user input.)
- `Agent`s should have a notion of whether they are complete or not (ie, if they have finished their task.)
- `Agent`s may ask questions, make suggestions, or provide other information to the user.
- `Agent`s must produce at least one output (eg, a branch, a file, a piece of text, etc.) when they are complete.
- `Agent`s, when complete, should have emitted at least one `UpdatedArtifactAgentMessage` to indicate the final output.
- `Agent`s, by convention, are run in a `tmux` session, and the user can connect to that session (over the web) to see the output.
  This is not strictly required, but it makes it easier to interact with (and debug) `Agent`s.

All of the above conventions are simply implemented by emitting and handling the correct `Message`s.

When emitting an artifact message that refers to some output to sync,
it is important that the artifact be written (and flushed) before the message is emitted.
Otherwise, the controlling process may read an inconsistent state of the artifact.

The most recent version of the `Agent` interface is `v1`.

See the [`./v1/agent.py`](./v1/agent.py) for the exact definition of the relevant message and config types.

In V1, the dependencies between the `Agent` and the `Environment` are not explicitly modeled --
the user is responsible for ensuring that the `Agent` can run in the specified `Environment`.

Note that while `Agent`s themselves are fairly general,
our existing `Agent` *runner* (i.e., the `Task` in `sculptor` that runs the `Agent` in an `Environment`)
does have a few more specific implementation details that are worth understanding.
See [`AgentTaskInputsV1`](/sculptor/sculptor/database/models.py) for those details.
