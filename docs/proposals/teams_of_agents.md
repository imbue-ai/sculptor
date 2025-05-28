# Supporting multiple agents for a given task

The current design already enables a variety of multi-agent workflows --
anything that can be expressed as a tree of tasks can be executed with the current system.
This includes having an agent that kicks off sub agents and waits for them,
as well as a manager agent that coordinates between multiple agents.

However, there are some limitations to the current design that make it difficult to express certain workflows.
For example, it is not currently possible to have multiple agents working on the same task at the same time
(without an explicit coordinator agent).
This could be done (poorly) in the current system by having multiple agents that happen to be sharing some resource
(but it would not be visible to the user that they were working on the same task).

We could either support such workflows by:
1. Making a sort of no-op coordinator agent that just shuffles all messages between the agents.
2. Splitting the `Task` object into a "user task" and a "computational task".
  We started with this split actually, but it felt more complicated than necessary.

For now let's see how far we can get with option 1, and we can always revisit this later if we need to.
