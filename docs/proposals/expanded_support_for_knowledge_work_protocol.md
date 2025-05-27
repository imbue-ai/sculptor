# KWP: Knowledge Work Protocol

At a high level, this system, as designed, is able to support far more than just coding tasks.

One idea is that we could make a sort of "knowledge work protocol" that describes the interface with agents that are doing useful knowledge work.

In particular, we already have to have the notion of agents being "blocked", having questions for the user, completing tasks, making suggestions for follow-up work, etc.

A task in our system is roughly like a linear ticket -- most of the various fields, statuses, what can happen, etc. are very similar in our own system.
In fact, for coding agents, we would even want to link to a PR, know whether it is in progress, in review, completed, merged, closed, etc.

But more broadly, most of the properties of a linear ticket also apply to our own system:
- there can be sub-tasks
- there are resulting artifacts (e.g., branches, code, documents, etc.)
- there could be comments or discussions (either with the agent or others)
- you would want the agent to provide an ETA for completion and/or cost, along with other status updates

It seems potentially worth developing some of this into a more formal protocol that we can use to communicate with agents doing knowledge work, and thus enable a much larger set of tasks to be handled by agents.

For example, making the notion of "is this actually successfully completed" into something first-class might make it easier to compose agents.

Clearly we dont want to be tied specifically to github or linear issues (there are many issue trackers).
Those are simply methods for *communicating* the status of a task -- the status and information is internal to our application / fundamental.
And clearly agents can have whatever rich internal state they want.
But the idea of the protocol would be to define a standard interface, and make it easier to compose a wide variety of agents.
