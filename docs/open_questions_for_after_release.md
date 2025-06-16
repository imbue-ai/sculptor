# Open design questions that we can answer after the initial release

There are a number of questions that we don't have to answer now, but will want to answer soon.

## How exactly does parallel pytest fit in?

I think this might be a better fit in the `pytest` check in `imbue_mcp`.

It would probably serve as a nice demo of "how you can launch a tool in a sandbox from our MCP server",
which is something that we want anyway.

Recursively invoking `Agent`s and tools *from our MCP server* is mostly about breaking out the module for the `Environment`s such that it can easily be invoked... via the CLI I guess?

## How exactly should snapshot/fork work?

This can be done by handling some special `Message`s (e.g., snapshot, fork, join) from the user in the `AgentTaskInputsV1` handler.

This seems like it ought to work reasonably well with the idea of `RequestCompleteAgentMessage` enabling snapshotting in the current design anyway.

One implication is that I'd like to keep the resume/snapshot tmux stuff in the execution logic for now, since it works and we're pretty sure we want to do this.

## How should we deal with migrations of the database?

I think for now we can get away with mostly just dropping data whenever we change the schema of any models.

Over time though (post-V1-release), we'll probably want to start getting a bit smarter and doing this the normal way.

## Should we explicitly model the goal of an agent?

With real work, goals are fundamentally flexible and iterative.
It is often the case that you start with one goal, but then end up with a different one.

When we are thinking about the goal of any particular agent, we need to consider this complexity.

The main question is whether this should be *explicit* or *implicit* in the design of our system.

**Tentative answer**: I'm pretty sure we *do* want to model the goal explicitly.
It seems fundamental to the nature of work and of doing a task at all.
Without having some goal, we cannot tell whether we have succeeded, and that's kind of core to what we're trying to do here.

## Should the agent be able to update the goal? (or only the user?)

*If* the goal is modeled explicitly,
we need to consider whether the agent should be able to update the goal itself,
or if only the user should be able to do that.

**Tentative answer**: seems like the agent probably should be able to update the goal.
Mostly because if we don't allow that, it's going to get pretty annoying to have to keep going in there and updating the goal manually.

And probably the agent should refrain from updating the goal unless:
1. it's pretty sure that makes sense.
2. it's *basically* the same goal, just more specific.

Perhaps, in a sense, updating the goal is sort of the same as making assumptions?
Maybe that's a better way to think about it...
