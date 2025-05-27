# `sculptor` architectural principles

There are a small number of principles and patterns that guide the architecture of the `sculptor` project.
These principles are not strict rules, but rather guidelines that help maintain a consistent and understandable codebase and approach to solving problems.

## Immutability

## Structured Concurrency

We try to use ["structured concurrency"](https://vorpus.org/blog/notes-on-structured-concurrency-or-go-statement-considered-harmful/) for all tasks and processes.
By doing this, we can prevent "zombie" processes and tasks, and make it easier to reason about the state of the system (for both users and developers.)

The `modal.App` primitive is a good example of this, as are `asyncio.TaskGroup`s.

Whenever we start remote `Environment`s, they are responsible for ensuring that they are shut down if the `Task` fails.

In practice, it's best to accomplish this with a sort of "dual" approach:
1. Any remote running resource should receive heartbeats from the controlling process.
  When the heartbeat stops, the remote resource should shut down.
2. The controlling process should, upon being restarted, check for any remote resources that are still running.
  If they are still running, it should attempt to resume them or shut them down.
  This is necessary because the remote resource heartbeat can get stuck.

Whenever possible, we should try to use the service-level primitives that are designed to handle this for us.
