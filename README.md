# Sculptor

[//]: # (<img src="images/sculptor-hero.png" width="70%">)

Sculptor is a desktop app for running coding agents in parallel. Each workspace is an isolated copy of your repo, so multiple tasks can progress at the same time without conflicts.

**Download:**
- [Mac (Apple Silicon)](https://tryimbue.link/sculptor-for-apple-silicon)
- [Linux](https://tryimbue.link/sculptor-for-linux)

**Getting started:** Connect a repo, create a workspace (an isolated clone), and prompt an agent to complete a task. When it's done, review the changes and merge them back into main. Create multiple agents in a workspace when you want fresh context or want agents to collaborate on the same problem.

> Report any bugs or leave any feedback as a [GitHub issue](https://github.com/imbue-ai/sculptor/issues/new).

---

## What's in these docs

- [Workspaces](docs/workspaces.md) — how workspaces map to repos and how to create one
- [Agents](docs/agents.md) — running multiple agents and tracking complex tasks
- [Interface](docs/interface.md) — the chat panel, model picker, file references, context window, and terminal
- [Actions](docs/actions.md) — saving prompts you use repeatedly
- [Changes](docs/changes.md) — reviewing and committing agent changes
- [Slash Commands](docs/slash-commands.md) — built-in commands and skills available in every session
- [Container Backend](docs/container-backend.md) — running the Sculptor backend in a Docker container or remote environment
