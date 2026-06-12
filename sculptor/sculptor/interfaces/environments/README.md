# `Environment` interface versions

At a high level, an `Environment` is a computational environment in which an `Agent` can run.

In practice, an `Environment` is the user's local working tree: agents run directly on
the host machine and operate on files in the workspace's working directory.

`Environment`s are responsible for cleaning up after themselves
(see "Structured Concurrency" in the [architectural principles.md]((/docs/architectural_principles.md)).

At a minimum, an `Environment` enables use to launch a `Process`, as well as read and write files.

The most recent version of the `Environment` interface is `v1`.

See `Environment` in [`./v1/environment.py`](./v1/environment.py) for the exact definition of the interface.
