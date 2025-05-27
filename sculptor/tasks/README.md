# sculptor task handlers

This module contains all the code for handling the various types of `TaskInput`s that can be created.

Each set of inputs is versioned so that when the types are changed while tasks are in progress,
the previous task can continue executing with the old type.

Currently, the only real task input type is `CodingAgentTaskInputsV1`,
which is handled in [`./handlers/coding_agent/v1.py`](./handlers/coding_agent/v1.py).
See the docstring for more information.
