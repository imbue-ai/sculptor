# History

We've been developing several iterations of coding agents at Imbue since GPT-4 first landed. We've learned a lot and thrown a lot away. Sculptor itself has gone through several iterations as well.

## Why did you build it this way?

Sculptor was initially designed and architected with a different vision in mind (see below). The reality is that our current codebase has some design choices that aren't perfectly aligned with its current implementation. It's been a fun and interesting challenge to take software that was primarily human-built for a different purpose and convert it to support agents and a new product vision.

We did consider rewriting from scratch, but felt the fastest and least risky route was to implement our changes in place. Full rewrites of a codebase were less commonplace at the time we made the decision (and are likely still difficult to do with user interfaces). Model capabilities were also worse.

## Why did we move away from running each agent in a Docker container?

- You get isolation at the cost of flexibility. We've found it very powerful to allow agents to inspect each other's work, and per-agent isolation gets in the way of that.
- Most users found the extra isolation confusing and more difficult to use.
- We've found it easier — and equivalent — to run the entire application in a container or VM instead of each agent. We support [this](help/experimental/container_backend.md) in the current version of Sculptor.
- We made the wrong choice relying on Docker Desktop (on macOS). Sculptor's performance hinged on a tool we didn't have much control over. Many new sandboxing options have been developed since we started that do a much better job, since they were designed specifically for this. We expect this to keep improving.
