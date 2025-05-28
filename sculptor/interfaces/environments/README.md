# `Environment` interface versions

At a high level, an `Environment` is a computational environment in which an `Agent` can run.

In practice, this ends up being a Docker container, a virtual machine, a sandbox, or some other isolated environment
where the agent can execute code, access files, and interact with the system.

`Environment`s are responsible for cleaning up after themselves
(see "Structured Concurrency" in the [architectural principles.md]((/docs/architectural_principles.md)).

At a minimum, an `Environment` enables use to launch a `Process`, as well as read and write files.

Many `Environment`s will also provide additional functionality,
such as the ability to snapshot and restore the environment's state.

The most recent version of the `Environment` interface is `v1`.

See `Environment` in [`./v1/environment.py`](./v1/environment.py) for the exact definition of the interface.
