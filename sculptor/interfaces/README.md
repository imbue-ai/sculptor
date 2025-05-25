# `sculptor` interfaces

Each interface is versioned so that the application can evolve without breaking existing functionality.
Version numbers are simple incrementing integers, starting from 1.
The module name contains the version number, e.g., `sculptor.interfaces.agents.v1`.

There is only one interface right now: `Agent`, which defines how the application interacts with AI agents.
See the [`agents/README.md`](./agents/README.md) for more details.
