# Open design questions that we can answer after the initial release

There are a number of questions that we don't have to answer now, but will want to answer soon.

## How exactly does parallel pytest fit in?

I think this might be a better fit in the `pytest` check in `imbue_mcp`.

It would probably serve as a nice demo of "how you can launch a tool in a sandbox from our MCP server",
which is something that we want anyway.

Recursively invoking `Agent`s and tools *from our MCP server* is mostly about breaking out the module for the `Environment`s such that it can easily be invoked... via the CLI I guess?

## How exactly should snapshot/fork work?

This can be done by handling some special `AgentMessage`s (e.g., snapshot, fork, join) from the user in the `AgentTaskInputsV1` handler.

This seems like it ought to work reasonably well with the idea of `RequestCompleteAgentMessage` enabling snapshotting in the current design anyway.

One implication is that I'd like to keep the resume/snapshot tmux stuff in the execution logic for now, since it works and we're pretty sure we want to do this.

## How should we deal with migrations of the database?

I think for now we can get away with mostly just dropping data whenever we change the schema of any models.

Over time though (post-V1-release), we'll probably want to start getting a bit smarter and doing this the normal way.
