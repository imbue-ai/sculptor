# `sculptor` interfaces

Each interface is versioned so that the application can evolve without breaking existing functionality.
Version numbers are simple incrementing integers, starting from 1.
The module name contains the version number, e.g., `sculptor.interfaces.agents.v1`.

The main interface right now is `Agent`.
It defines the required methods for communicating with some agent in order to perform a `Task`.
See the [`agents/README.md`](./agents/README.md) for more details.

`Agent`s are typically executed in a sandboxed `Environment`.
The interfaces `Environment`s is defined in the [`environments/README.md`](./environments/README.md).
